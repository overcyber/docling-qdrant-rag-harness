#!/usr/bin/env python3
"""Batch document ingestion script for Docling Qdrant RAG Harness.

Reads PDF and other supported documents from a directory and submits them
to the unified FastAPI /v1/documents endpoint, tracking jobs until completion.
Includes pre-flight GPU acceleration check, local SHA-256 duplicate verification,
and automatic skipping of already ingested documents.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def check_gpu_and_readiness(api_url: str, api_key: str | None = None) -> dict:
    url = f"{api_url.rstrip('/')}/ready"
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {}


def check_already_ingested(
    api_url: str,
    tenant_id: str,
    sha256: str,
    corpus_id: str | None = None,
    api_key: str | None = None,
) -> dict:
    params = {"sha256": sha256}
    if corpus_id:
        params["corpus_id"] = corpus_id
    url = f"{api_url.rstrip('/')}/v1/documents/check?{urllib.parse.urlencode(params)}"
    headers = {"X-Tenant-ID": tenant_id}
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {"exists": False}


def submit_document(
    api_url: str,
    file_path: Path,
    tenant_id: str,
    corpus_id: str,
    chunker: str,
    max_tokens: int,
    do_ocr: bool,
    force: bool,
    api_key: str | None = None,
) -> dict:
    url = f"{api_url.rstrip('/')}/v1/documents"
    boundary = "----DoclingFormBoundary" + str(int(time.time() * 1000))

    metadata = json.dumps({
        "source_folder": str(file_path.parent),
        "filename": file_path.name,
    })
    proc_opts = json.dumps({
        "chunking": {"type": chunker, "max_tokens": max_tokens},
        "pdf": {"do_ocr": do_ocr, "do_table_structure": True},
        "deduplicate": not force,
    })

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    body = bytearray()
    # Corpus ID field
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="corpus_id"\r\n\r\n')
    body.extend(corpus_id.encode() + b"\r\n")

    # Metadata field
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="metadata"\r\n\r\n')
    body.extend(metadata.encode() + b"\r\n")

    # Processing options field
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="processing_options"\r\n\r\n')
    body.extend(proc_opts.encode() + b"\r\n")

    # File field
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode())
    body.extend(b"Content-Type: application/pdf\r\n\r\n")
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "X-Tenant-ID": tenant_id,
    }
    if api_key:
        headers["X-API-Key"] = api_key

    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers=headers,
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def poll_job(api_url: str, job_id: str, tenant_id: str, api_key: str | None = None, timeout: int = 600) -> dict:
    url = f"{api_url.rstrip('/')}/v1/jobs/{job_id}"
    headers = {"X-Tenant-ID": tenant_id}
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, headers=headers)
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                state = data.get("state")
                if state in {"SUCCESS", "FAILURE"}:
                    return data
        except Exception:
            pass
        time.sleep(2)
    return {"state": "TIMEOUT", "error": f"Exceeded {timeout}s waiting for job"}


def process_single(
    api_url: str,
    file_path: Path,
    tenant_id: str,
    corpus_id: str,
    chunker: str,
    max_tokens: int,
    do_ocr: bool,
    force: bool,
    api_key: str | None = None,
) -> dict:
    try:
        sha256 = compute_sha256(file_path)

        # 1. Fast pre-check: verify if document with this SHA-256 is already in Qdrant
        if not force:
            check_res = check_already_ingested(api_url, tenant_id, sha256, corpus_id, api_key)
            if check_res.get("exists"):
                return {
                    "file": file_path.name,
                    "status": "ALREADY_INGESTED",
                    "document_id": check_res.get("document_id"),
                    "sha256": sha256,
                    "corpus_id": check_res.get("corpus_id"),
                    "pre_checked": True,
                }

        # 2. Submit document upload
        sub = submit_document(
            api_url=api_url,
            file_path=file_path,
            tenant_id=tenant_id,
            corpus_id=corpus_id,
            chunker=chunker,
            max_tokens=max_tokens,
            do_ocr=do_ocr,
            force=force,
            api_key=api_key,
        )

        # Check if server-side deduplication caught it
        if sub.get("status") in {"duplicate", "duplicate_pending"}:
            return {
                "file": file_path.name,
                "status": "ALREADY_INGESTED",
                "document_id": sub.get("duplicate_of") or sub.get("document_id"),
                "sha256": sub.get("sha256") or sha256,
                "corpus_id": sub.get("corpus_id") or corpus_id,
                "pre_checked": False,
            }

        job_id = sub.get("job_id")
        if not job_id:
            return {"file": file_path.name, "status": "FAILED_SUBMIT", "error": sub}

        # 3. Poll Celery worker completion
        job_res = poll_job(api_url, job_id, tenant_id, api_key=api_key)
        state = job_res.get("state")
        if state == "SUCCESS":
            res = job_res.get("result", {})
            return {
                "file": file_path.name,
                "status": "SUCCESS",
                "document_id": res.get("document_id"),
                "chunks": res.get("chunks", 0),
                "accelerator": res.get("accelerator"),
                "accelerator_device": res.get("accelerator_device"),
                "parse_duration_seconds": res.get("parse_duration_seconds"),
            }
        else:
            return {"file": file_path.name, "status": state, "detail": job_res}
    except Exception as exc:
        return {"file": file_path.name, "status": "ERROR", "error": str(exc)}


def main():
    parser = argparse.ArgumentParser(
        description="Ingest directory of documents into Docling Qdrant RAG Harness with automatic duplicate detection and GPU verification."
    )
    parser.add_argument("--dir", default="/opt/pdf-ingestao", help="Directory containing documents")
    parser.add_argument("--api", default="http://localhost:8000", help="Harness API URL")
    parser.add_argument("--tenant", default="mestrado-cybersec", help="Tenant ID")
    parser.add_argument("--corpus", "--corpus-id", dest="corpus", default="default", help="Logical corpus namespace")
    parser.add_argument("--api-key", default=os.getenv("API_KEY", ""), help="API Key for Harness authentication")
    parser.add_argument("--chunker", default="hybrid", choices=["hybrid", "hierarchical", "line_based"])
    parser.add_argument("--max-tokens", type=int, default=120)
    parser.add_argument("--ocr", action="store_true", default=False, help="Enable OCR (slower, for scanned PDFs)")
    parser.add_argument("--force", action="store_true", default=False, help="Force re-ingestion of already processed files")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of documents to ingest")
    parser.add_argument("--concurrency", type=int, default=2, help="Number of concurrent uploads/polling")
    args = parser.parse_args()

    p = Path(args.dir)
    if not p.exists() or not p.is_dir():
        print(f"Error: Directory {args.dir} does not exist.", file=sys.stderr)
        sys.exit(1)

    files = sorted([f for f in p.iterdir() if f.is_file() and f.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}])
    if args.limit:
        files = files[:args.limit]

    # Pre-flight check: API & GPU readiness
    readiness = check_gpu_and_readiness(args.api, args.api_key)
    checks = readiness.get("checks", {})
    parser_cuda = checks.get("parser_cuda", False)
    parser_device = checks.get("parser_device", "CPU / Not detected")

    print("=" * 75)
    print(f"📁 Diretório:    {args.dir} ({len(files)} arquivos)")
    print(f"🏢 Tenant:       {args.tenant} | Corpus: {args.corpus}")
    print(f"⚙️  Chunker:      {args.chunker} (max_tokens: {args.max_tokens}) | OCR: {args.ocr}")
    print(f"🔄 Concorrência: {args.concurrency} | Forçar Reingestão: {args.force}")
    if parser_cuda:
        print(f"🚀 Aceleração:   CUDA ATIVO ({parser_device})")
    else:
        print(f"⚠️  Aceleração:   {parser_device} (CPU)")
    print("=" * 75)

    start_all = time.time()
    success_count = 0
    already_ingested_count = 0
    fail_count = 0
    total_chunks = 0

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {
            executor.submit(
                process_single,
                args.api,
                f,
                args.tenant,
                args.corpus,
                args.chunker,
                args.max_tokens,
                args.ocr,
                args.force,
                args.api_key or None,
            ): f
            for f in files
        }
        for idx, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            status = res.get("status")
            fname = res.get("file")
            if status == "SUCCESS":
                success_count += 1
                chunks = res.get("chunks", 0)
                total_chunks += chunks
                accel = res.get("accelerator", "cpu")
                accel_dev = res.get("accelerator_device", "")
                dur = res.get("parse_duration_seconds", 0)
                accel_str = f" [GPU: {accel_dev}]" if accel == "cuda" else " [CPU]"
                dur_str = f" em {dur:.1f}s" if dur else ""
                print(f"[{idx}/{len(files)}] ✅ NOVO INGERIDO: {fname} -> {chunks} chunks{accel_str}{dur_str} (ID: {res['document_id']})")
            elif status == "ALREADY_INGESTED":
                already_ingested_count += 1
                pre = " [pre-check instantâneo]" if res.get("pre_checked") else ""
                print(f"[{idx}/{len(files)}] ⏭️  JÁ INGERIDO (IGNORADO): {fname}{pre} (ID existente: {res['document_id']})")
            else:
                fail_count += 1
                print(f"[{idx}/{len(files)}] ❌ FALHA: {fname} -> {res.get('error') or res.get('status')}")

    total_time = time.time() - start_all
    print("=" * 75)
    print(f"🏁 Concluído em {total_time:.1f}s")
    print(
        f"📊 Resumo: Novos Ingeridos: {success_count} | Já Ingeridos (Ignorados): {already_ingested_count} | "
        f"Falhas: {fail_count} | Novos Chunks: {total_chunks}"
    )


if __name__ == "__main__":
    main()
