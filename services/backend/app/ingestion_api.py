from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

from celery.result import AsyncResult
import redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from .auth import require_auth, tenant_id
from .celery_app import celery_app
from .config import settings
from .qdrant_store import (
    delete_document,
    find_document_by_fingerprint,
    list_document_chunks,
)
from .schemas import ProcessingOptions, TextIngestRequest
from .state_keys import ingest_reservation_key, job_owner_key
from .tasks import ingest_document

router = APIRouter(prefix="/v1", tags=["documents"], dependencies=[Depends(require_auth)])
SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".markdown"}
rdb = redis.Redis.from_url(settings.redis_url, decode_responses=True)


try:
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
except OSError:
    pass


def parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("metadata must be a JSON object")
        return value
    except Exception as exc:
        raise HTTPException(400, f"Invalid metadata JSON: {exc}") from exc


def parse_processing_options(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        model = ProcessingOptions.model_validate(value)
        return model.model_dump(mode="json", exclude_none=True)
    except Exception as exc:
        raise HTTPException(400, f"Invalid processing_options JSON: {exc}") from exc


def effective_ingestion_profile(processing_options: dict[str, Any]) -> dict[str, Any]:
    """Resolve only settings that change parsing/chunking/index semantics.

    Queue-control options such as ``deduplicate`` are intentionally excluded.
    This mirrors the parser defaults closely enough for deterministic deduplication
    before the asynchronous parser has run.
    """
    requested_chunking = dict(processing_options.get("chunking") or {})
    kind = str(requested_chunking.get("type") or settings.chunker_type)

    if kind == "hierarchical":
        chunking: dict[str, Any] = {
            "type": "hierarchical",
            "merge_list_items": settings.chunk_hierarchical_merge_list_items,
            "always_emit_headings": settings.chunk_hierarchical_always_emit_headings,
        }
    elif kind == "line_based":
        chunking = {
            "type": "line_based",
            "tokenizer_model": settings.chunk_tokenizer_model,
            "max_tokens": settings.chunk_max_tokens,
            "prefix": settings.chunk_line_prefix,
            "omit_prefix_on_overflow": settings.chunk_line_omit_prefix_on_overflow,
        }
    else:
        chunking = {
            "type": "hybrid",
            "tokenizer_model": settings.chunk_tokenizer_model,
            "max_tokens": settings.chunk_max_tokens,
            "merge_peers": settings.chunk_hybrid_merge_peers,
            "repeat_table_header": settings.chunk_hybrid_repeat_table_header,
            "omit_header_on_overflow": settings.chunk_hybrid_omit_header_on_overflow,
            "always_emit_headings": settings.chunk_hybrid_always_emit_headings,
        }
    chunking.update({k: v for k, v in requested_chunking.items() if v is not None})

    pdf = {
        "do_ocr": settings.pdf_do_ocr,
        "do_table_structure": settings.pdf_do_table_structure,
        "do_cell_matching": settings.pdf_do_cell_matching,
    }
    pdf.update({k: v for k, v in dict(processing_options.get("pdf") or {}).items() if v is not None})

    conversion: dict[str, Any] = {
        "max_num_pages": settings.docling_max_num_pages,
        "page_range": None,
    }
    conversion.update(
        {k: v for k, v in dict(processing_options.get("conversion") or {}).items() if v is not None}
    )
    return {
        "chunking": chunking,
        "pdf": pdf,
        "conversion": conversion,
        "parser_full_docling_metadata": settings.parser_full_docling_metadata,
        "text_fallback_max_tokens": settings.chunk_max_tokens,
        "embedding": {
            "dense": settings.dense_model,
            "sparse": settings.sparse_model,
            "bm25_language": settings.bm25_language,
        },
    }


def normalize_corpus_id(value: str | None) -> str:
    corpus_id = (value or settings.default_corpus_id).strip()
    if not corpus_id or len(corpus_id) > 128 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", corpus_id):
        raise HTTPException(400, "corpus_id must match [A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
    return corpus_id


def ingest_fingerprint(sha256: str, corpus_id: str, user_metadata: dict[str, Any], processing_options: dict[str, Any]) -> str:
    """Fingerprint source bytes + corpus + effective parser profile + retrieval metadata."""
    canonical = json.dumps(
        {
            "source_sha256": sha256,
            "corpus_id": corpus_id,
            "effective_processing_profile": effective_ingestion_profile(processing_options),
            "user_metadata": user_metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_tenant_dir(tenant: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", tenant):
        raise HTTPException(400, "Invalid tenant path")
    upload_root = Path(settings.upload_dir).resolve()
    tenant_dir = (upload_root / tenant).resolve()
    try:
        tenant_dir.relative_to(upload_root)
    except ValueError as exc:
        raise HTTPException(400, "Invalid tenant path") from exc
    tenant_dir.mkdir(parents=True, exist_ok=True)
    return tenant_dir


async def save_upload(file: UploadFile, tenant: str) -> tuple[str, str, str, int, str]:
    filename = Path(file.filename or "document").name
    raw_suffix = Path(filename).suffix.lower()
    suffix_map = {
        ".pdf": ".pdf",
        ".docx": ".docx",
        ".txt": ".txt",
        ".md": ".md",
        ".markdown": ".markdown",
    }
    final_suffix = suffix_map.get(raw_suffix)
    if not final_suffix:
        raise HTTPException(415, f"Unsupported extension {raw_suffix}; allowed: {sorted(SUPPORTED)}")

    document_id = str(uuid.uuid4())
    tenant_dir = resolve_tenant_dir(tenant)
    path = (tenant_dir / f"{document_id}{final_suffix}").resolve()
    try:
        path.relative_to(tenant_dir)
    except ValueError as exc:
        raise HTTPException(400, "Invalid upload path") from exc
    h = hashlib.sha256()
    size = 0
    limit = settings.max_file_mb * 1024 * 1024
    read_size = max(64 * 1024, settings.api_upload_buffer_mb * 1024 * 1024)

    try:
        with path.open("wb") as out:
            while True:
                chunk = await file.read(read_size)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File exceeds {settings.max_file_mb} MB")
                h.update(chunk)
                out.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise

    return document_id, str(path), h.hexdigest(), size, filename


def queue_document(
    *,
    document_id: str,
    tenant: str,
    corpus_id: str,
    path: str,
    filename: str,
    sha256: str,
    size: int,
    user_metadata: dict[str, Any],
    processing_options: dict[str, Any],
) -> dict[str, Any]:
    deduplicate = processing_options.get("deduplicate")
    if deduplicate is None:
        deduplicate = settings.default_deduplicate
    fingerprint = ingest_fingerprint(sha256, corpus_id, user_metadata, processing_options)
    job_id = str(uuid.uuid4())
    reservation_key: str | None = None

    try:
        if deduplicate:
            existing = find_document_by_fingerprint(tenant, fingerprint)
            if existing:
                Path(path).unlink(missing_ok=True)
                payload = existing["payload"]
                return {
                    "document_id": payload.get("document_id"),
                    "job_id": None,
                    "sha256": sha256,
                    "filename": payload.get("filename", filename),
                    "corpus_id": payload.get("corpus_id", corpus_id),
                    "bytes": size,
                    "status": "duplicate",
                    "duplicate_of": payload.get("document_id"),
                    "ingest_fingerprint": fingerprint,
                }

            reservation_key = ingest_reservation_key(tenant, fingerprint)
            reservation = json.dumps(
                {"document_id": document_id, "job_id": job_id, "filename": filename},
                separators=(",", ":"),
            )
            acquired = bool(
                rdb.set(
                    reservation_key,
                    reservation,
                    nx=True,
                    ex=settings.dedupe_pending_ttl_seconds,
                )
            )
            if not acquired:
                Path(path).unlink(missing_ok=True)
                pending_raw = rdb.get(reservation_key)
                try:
                    pending = json.loads(pending_raw) if pending_raw else {}
                except Exception:
                    pending = {}
                return {
                    "document_id": pending.get("document_id"),
                    "job_id": pending.get("job_id"),
                    "sha256": sha256,
                    "filename": pending.get("filename", filename),
                    "corpus_id": corpus_id,
                    "bytes": size,
                    "status": "duplicate_pending",
                    "duplicate_of": pending.get("document_id"),
                    "ingest_fingerprint": fingerprint,
                }

        rdb.setex(job_owner_key(job_id), settings.job_owner_ttl_seconds, tenant)
        ingest_document.apply_async(
            kwargs={
                "document_id": document_id,
                "tenant_id": tenant,
                "corpus_id": corpus_id,
                "file_path": path,
                "filename": filename,
                "sha256": sha256,
                "ingest_fingerprint": fingerprint,
                "user_metadata": user_metadata,
                "processing_options": processing_options,
            },
            task_id=job_id,
        )
    except Exception:
        try:
            rdb.delete(job_owner_key(job_id))
            if reservation_key is not None:
                rdb.delete(reservation_key)
        except Exception:
            pass
        Path(path).unlink(missing_ok=True)
        raise

    return {
        "document_id": document_id,
        "job_id": job_id,
        "sha256": sha256,
        "ingest_fingerprint": fingerprint,
        "filename": filename,
        "corpus_id": corpus_id,
        "bytes": size,
        "status": "queued",
        "processing_options": processing_options,
    }


@router.post(
    "/documents",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest one document asynchronously",
    description=(
        "Uploads a PDF, DOCX, TXT or Markdown file, queues Docling parsing, chunking, "
        "embedding and Qdrant indexing. `processing_options` is a JSON object and can "
        "select hybrid, hierarchical or line_based chunking for this document."
    ),
)
async def upload_document(
    file: UploadFile = File(..., description="PDF, DOCX, TXT, MD or MARKDOWN file"),
    corpus_id: str | None = Form(default=None, description="Logical corpus namespace; defaults to DEFAULT_CORPUS_ID"),
    metadata: str | None = Form(default=None, description="Arbitrary JSON metadata stored in Qdrant"),
    processing_options: str | None = Form(
        default=None,
        description="JSON ProcessingOptions; see GET /v1/config/chunkers and docs/chunking.md",
        examples=[
            '{"chunking":{"type":"hybrid","max_tokens":120}}',
            '{"chunking":{"type":"hierarchical"}}',
            '{"chunking":{"type":"line_based","max_tokens":120}}',
        ],
    ),
    tenant: str = Depends(tenant_id),
):
    user_metadata = parse_metadata(metadata)
    options = parse_processing_options(processing_options)
    corpus = normalize_corpus_id(corpus_id)
    document_id, path, sha256, size, filename = await save_upload(file, tenant)
    return queue_document(
        document_id=document_id,
        tenant=tenant,
        corpus_id=corpus,
        path=path,
        filename=filename,
        sha256=sha256,
        size=size,
        user_metadata=user_metadata,
        processing_options=options,
    )


@router.post(
    "/documents/text",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest raw text through the same asynchronous Docling/chunking pipeline",
)
def ingest_text(req: TextIngestRequest, tenant: str = Depends(tenant_id)):
    corpus = normalize_corpus_id(req.corpus_id)
    document_id = str(uuid.uuid4())
    tenant_dir = resolve_tenant_dir(tenant)

    requested = Path(req.filename or "").name
    if requested.lower().endswith(".txt"):
        final_suffix = ".txt"
        filename = requested
    elif requested.lower().endswith(".markdown"):
        final_suffix = ".markdown"
        filename = requested
    elif requested.lower().endswith(".md"):
        final_suffix = ".md"
        filename = requested
    elif requested:
        final_suffix = ".md"
        filename = f"{requested}.md"
    else:
        safe_title = re.sub(r"[^A-Za-z0-9._-]+", "-", (req.title or "text-document")).strip("-._")[:120]
        filename = f"{safe_title or 'text-document'}.md"
        final_suffix = ".md"

    path = (tenant_dir / f"{document_id}{final_suffix}").resolve()
    try:
        path.relative_to(tenant_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid output path") from exc
    raw = req.text.encode("utf-8")
    limit = settings.max_file_mb * 1024 * 1024
    if len(raw) > limit:
        raise HTTPException(413, f"Text exceeds {settings.max_file_mb} MB")
    path.write_bytes(raw)
    metadata = dict(req.metadata)
    if req.title:
        metadata.setdefault("title", req.title)
    options = req.processing_options.model_dump(mode="json", exclude_none=True)
    return queue_document(
        document_id=document_id,
        tenant=tenant,
        corpus_id=corpus,
        path=str(path),
        filename=filename,
        sha256=hashlib.sha256(raw).hexdigest(),
        size=len(raw),
        user_metadata=metadata,
        processing_options=options,
    )


@router.post(
    "/documents/batch",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest multiple documents",
)
async def upload_batch(
    files: list[UploadFile] = File(...),
    corpus_id: str | None = Form(default=None),
    metadata: str | None = Form(default=None),
    processing_options: str | None = Form(default=None),
    tenant: str = Depends(tenant_id),
):
    if len(files) > settings.api_max_batch_files:
        raise HTTPException(400, f"Maximum {settings.api_max_batch_files} files per batch request")

    user_metadata = parse_metadata(metadata)
    options = parse_processing_options(processing_options)
    corpus = normalize_corpus_id(corpus_id)
    jobs: list[dict[str, Any]] = []
    for file in files:
        document_id, path, sha256, size, filename = await save_upload(file, tenant)
        jobs.append(
            queue_document(
                document_id=document_id,
                tenant=tenant,
                corpus_id=corpus,
                path=path,
                filename=filename,
                sha256=sha256,
                size=size,
                user_metadata=user_metadata,
                processing_options=options,
            )
        )
    return {"count": len(jobs), "jobs": jobs}


@router.get("/jobs/{job_id}", summary="Get asynchronous ingestion job status")
def job_status(job_id: str, tenant: str = Depends(tenant_id)):
    owner = rdb.get(job_owner_key(job_id))
    if owner != tenant:
        # Do not reveal whether a job exists for another tenant.
        raise HTTPException(404, "Job not found")
    result = AsyncResult(job_id, app=celery_app)
    body: dict[str, Any] = {"job_id": job_id, "state": result.state}
    if result.state == "SUCCESS":
        body["result"] = result.result
    elif result.state == "FAILURE":
        body["error"] = str(result.result)
    elif result.info:
        body["progress"] = result.info
    return body


@router.get("/documents/{document_id}", summary="Inspect indexed chunks for one document")
def get_document(
    document_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    tenant: str = Depends(tenant_id),
):
    try:
        uuid.UUID(document_id)
    except ValueError as exc:
        raise HTTPException(400, "document_id must be a UUID") from exc

    rows = list_document_chunks(tenant, document_id, limit=limit)
    if not rows:
        raise HTTPException(404, "Document not found")
    first = rows[0]["payload"]
    chunks = [
        {
            "chunk_index": r["payload"].get("chunk_index"),
            "pages": r["payload"].get("pages", []),
            "headings": r["payload"].get("headings", []),
            "text": r["payload"].get("text", ""),
        }
        for r in rows
    ]
    return {
        "document_id": document_id,
        "tenant_id": tenant,
        "filename": first.get("filename"),
        "corpus_id": first.get("corpus_id", settings.default_corpus_id),
        "sha256": first.get("sha256"),
        "chunker_type": first.get("chunker_type"),
        "chunking_config": first.get("chunking_config", {}),
        "metadata": first.get("user_metadata", {}),
        "chunks": chunks,
        "returned_chunks": len(chunks),
    }


@router.delete("/documents/{document_id}", summary="Delete one document from Qdrant and local upload storage")
def remove_document(document_id: str, tenant: str = Depends(tenant_id)):
    try:
        uuid.UUID(document_id)
    except ValueError as exc:
        raise HTTPException(400, "document_id must be a UUID") from exc
    delete_document(tenant, document_id)
    tenant_dir = resolve_tenant_dir(tenant)
    for candidate in tenant_dir.glob(f"{document_id}.*"):
        try:
            candidate.resolve().relative_to(tenant_dir)
            candidate.unlink(missing_ok=True)
        except ValueError:
            pass
    return {"status": "deleted", "document_id": document_id, "tenant_id": tenant}
