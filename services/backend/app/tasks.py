from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Iterable

import httpx
import redis
from celery import Task
from qdrant_client import models

from .celery_app import celery_app
from .config import settings
from .event_bus import publish_event
from .qdrant_store import client as qdrant_client, delete_document, ensure_collection
from .state_keys import ingest_reservation_key


def batched(items: list[Any], size: int) -> Iterable[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def release_ingest_reservation(tenant_id: str, ingest_fingerprint: str) -> None:
    try:
        redis.Redis.from_url(settings.redis_url).delete(ingest_reservation_key(tenant_id, ingest_fingerprint))
    except Exception:
        pass


class IngestTask(Task):
    """Celery task base that releases only terminal failed-ingestion reservations."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):  # noqa: ANN001
        tenant_id = kwargs.get("tenant_id")
        fingerprint = kwargs.get("ingest_fingerprint")
        if tenant_id and fingerprint:
            release_ingest_reservation(str(tenant_id), str(fingerprint))
        publish_event("document.failed", {
            "job_id": task_id,
            "tenant_id": tenant_id,
            "document_id": kwargs.get("document_id"),
            "corpus_id": kwargs.get("corpus_id"),
            "error": f"{type(exc).__name__}: {exc}",
        })
        super().on_failure(exc, task_id, args, kwargs, einfo)


@celery_app.task(bind=True, base=IngestTask, name="ingest_document", max_retries=3)
def ingest_document(
    self,
    *,
    document_id: str,
    tenant_id: str,
    corpus_id: str,
    file_path: str,
    filename: str,
    sha256: str,
    ingest_fingerprint: str,
    user_metadata: dict[str, Any] | None = None,
    processing_options: dict[str, Any] | None = None,
):
    path = Path(file_path).resolve()
    upload_root = Path(settings.upload_dir).resolve()
    try:
        path.relative_to(upload_root)
    except ValueError as exc:
        raise ValueError(f"Ingestion path {file_path} is outside upload directory") from exc
    if not path.exists():
        raise FileNotFoundError(file_path)
    processing_options = processing_options or {}
    try:
        publish_event("document.started", {"job_id": self.request.id, "tenant_id": tenant_id, "document_id": document_id, "corpus_id": corpus_id})
        self.update_state(state="PROGRESS", meta={"stage": "parsing", "progress": 10})
        with path.open("rb") as fh, httpx.Client(timeout=httpx.Timeout(float(settings.parser_timeout_seconds), connect=15.0)) as http:
            resp = http.post(
                f"{settings.parser_url}/parse",
                files={"file": (filename, fh, "application/octet-stream")},
                data={"options": json.dumps(processing_options, ensure_ascii=False)},
            )
            resp.raise_for_status()
            parsed = resp.json()
        chunks = parsed.get("chunks") or []
        if not chunks:
            raise RuntimeError("Parser returned zero chunks")
        self.update_state(state="PROGRESS", meta={"stage": "embedding", "progress": 35, "chunks": len(chunks)})
        dense_all: list[list[float]] = []
        sparse_all: list[dict[str, list]] = []
        embedding_identity: dict[str, Any] | None = None
        texts = [c["contextualized_text"] for c in chunks]
        with httpx.Client(timeout=httpx.Timeout(float(settings.embedder_timeout_seconds), connect=15.0)) as http:
            for group in batched(texts, settings.embedding_batch_size):
                r = http.post(f"{settings.embedder_url}/embed/documents", json={"texts": group})
                r.raise_for_status()
                payload = r.json()
                current_identity = payload.get("models") or {}
                if embedding_identity is None:
                    embedding_identity = current_identity
                elif current_identity and current_identity != embedding_identity:
                    raise RuntimeError("Embedding service model identity changed during one ingestion")
                dense_all.extend(payload["dense"])
                sparse_all.extend(payload["sparse"])
        if not (len(chunks) == len(dense_all) == len(sparse_all)):
            raise RuntimeError("Embedding cardinality mismatch")
        self.update_state(state="PROGRESS", meta={"stage": "indexing", "progress": 70})
        ensure_collection(dense_size=len(dense_all[0]), embedding_identity=embedding_identity)
        delete_document(tenant_id, document_id)
        qc = qdrant_client()
        points: list[models.PointStruct] = []
        namespace = uuid.UUID(document_id)
        for i, (chunk, dense, sparse) in enumerate(zip(chunks, dense_all, sparse_all)):
            point_id = str(uuid.uuid5(namespace, f"chunk:{i}"))
            meta = chunk.get("metadata", {})
            payload = {
                "tenant_id": tenant_id,
                "corpus_id": corpus_id,
                "document_id": document_id,
                "sha256": sha256,
                "ingest_fingerprint": ingest_fingerprint,
                "filename": filename,
                "chunk_index": i,
                "text": chunk["text"],
                "contextualized_text": chunk["contextualized_text"],
                "headings": meta.get("headings", []),
                "pages": meta.get("pages", []),
                "page_provenance": meta.get("page_provenance", "chunk"),
                "docling_metadata": meta.get("docling", {}),
                "parser_fallback": meta.get("fallback", False),
                "embedding_models": embedding_identity or {"dense": settings.dense_model, "sparse": settings.sparse_model, "bm25_language": settings.bm25_language},
                "chunker_type": parsed.get("chunker_type"),
                "chunking_config": parsed.get("chunking_config", {}),
                "processing_options": parsed.get("processing_options", processing_options),
                "user_metadata": user_metadata or {},
            }
            points.append(models.PointStruct(
                id=point_id,
                vector={
                    "dense": dense,
                    "sparse": models.SparseVector(indices=[int(x) for x in sparse["indices"]], values=[float(x) for x in sparse["values"]]),
                },
                payload=payload,
            ))
        total = len(points)
        for idx, group in enumerate(batched(points, 128)):
            qc.upsert(collection_name=settings.qdrant_collection, points=group, wait=True)
            progress = 70 + int(25 * min((idx + 1) * 128, total) / total)
            self.update_state(state="PROGRESS", meta={"stage": "indexing", "progress": progress, "indexed": min((idx + 1) * 128, total), "chunks": total})
        result = {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "corpus_id": corpus_id,
            "filename": filename,
            "sha256": sha256,
            "ingest_fingerprint": ingest_fingerprint,
            "chunks": total,
            "status": "indexed",
            "chunker_type": parsed.get("chunker_type"),
            "chunking_config": parsed.get("chunking_config", {}),
            "parser_warning": parsed.get("warning"),
            "embedding_models": embedding_identity,
        }
        if settings.delete_source_after_ingest:
            path.unlink(missing_ok=True)
        release_ingest_reservation(tenant_id, ingest_fingerprint)
        publish_event("document.indexed", {"job_id": self.request.id, "tenant_id": tenant_id, "document_id": document_id, "corpus_id": corpus_id, "filename": filename, "chunks": total})
        return result
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        raise self.retry(exc=exc, countdown=min(60, 2 ** self.request.retries * 5))
