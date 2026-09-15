#!/usr/bin/env python3
"""Batch document ingestion script for Docling Qdrant RAG Harness.

Reads PDF and other supported documents from a directory and submits them
to the unified FastAPI /v1/documents endpoint, tracking jobs until completion.
Automatically detects already ingested files and skips redundant processing.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import urllib.request
import urllib.error

def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def submit_document(
    api_url: str,
    file_path: Path,
    tenant_id: str,
    chunker: str,
    max_tokens: int,
    do_ocr: bool,
    force: bool,
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

    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Tenant-ID": tenant_id,
        },
        method="POST"
    )
    
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())

def poll_job(api_url: str, job_id: str, tenant_id: str, timeout: int = 600) -> dict:
    url = f"{api_url.rstrip('/')}/v1/jobs/{job_id}"
    req = urllib.request.Request(url, headers={"X-Tenant-ID": tenant_id})
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
    chunker: str,
    max_tokens: int,
    do_ocr: bool,
    force: bool,
) -> dict:
    try:
        sub = submit_document(api_url, file_path, tenant_id, chunker, max_tokens, do_ocr, force)
        
        # Check if already ingested (duplicate detected by API deduplication)
        if sub.get("status") in {"duplicate", "duplicate_pending"}:
            return {
                "file": file_path.name,
                "status": "ALREADY_INGESTED",
                "document_id": sub.get("duplicate_of") or sub.get("document_id"),
                "sha256": sub.get("sha256"),
            }

        job_id = sub.get("job_id")
        if not job_id:
            return {"file": file_path.name, "status": "FAILED_SUBMIT", "error": sub}

        job_res = poll_job(api_url, job_id, tenant_id)
        state = job_res.get("state")
        if state == "SUCCESS":
            res = job_res.get("result", {})
            return {
                "file": file_path.name,
                "status": "SUCCESS",
                "document_id": res.get("document_id"),
                "chunks": res.get("chunks", 0),
            }
        else:
            return {"file": file_path.name, "status": state, "detail": job_res}
    except Exception as exc:
        return {"file": file_path.name, "status": "ERROR", "error": str(exc)}

def main():
    parser = argparse.ArgumentParser(description="Ingest directory of documents into Docling Qdrant RAG Harness with automatic duplicate detection.")
    parser.add_argument("--dir", default="/opt/pdf-ingestao", help="Directory containing documents")
    parser.add_argument("--api", default="http://localhost:8000", help="Harness API URL")
    parser.add_argument("--tenant", default="mestrado-cybersec", help="Tenant ID")
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

    print(f"Directory: {args.dir} ({len(files)} files)")
    print(f"Tenant: {args.tenant} | Chunker: {args.chunker} (max_tokens: {args.max_tokens})")
    print(f"Concurrency: {args.concurrency} | OCR: {args.ocr} | Force Re-ingest: {args.force}")
    print("=" * 70)

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
                args.chunker,
                args.max_tokens,
                args.ocr,
                args.force,
            ): f
            for f in files
        }
        for idx, fut in enumerate(as_completed(futures), 1):
            fpath = futures[fut]
            res = fut.result()
            status = res.get("status")
            if status == "SUCCESS":
                success_count += 1
                chunks = res.get("chunks", 0)
                total_chunks += chunks
                print(f"[{idx}/{len(files)}] NOVO INGERIDO: {res['file']} -> {chunks} chunks (ID: {res['document_id']})")
            elif status == "ALREADY_INGESTED":
                already_ingested_count += 1
                print(f"[{idx}/{len(files)}] JÁ INGERIDO (IGNORADO): {res['file']} (ID existente: {res['document_id']})")
            else:
                fail_count += 1
                print(f"[{idx}/{len(files)}] FALHA: {res.get('file')} -> {res}")

    total_time = time.time() - start_all
    print("=" * 70)
    print(f"Concluído em {total_time:.1f}s")
    print(f"Novos Ingeridos: {success_count} | Já Ingeridos (Ignorados): {already_ingested_count} | Falhas: {fail_count} | Novos Chunks: {total_chunks}")

if __name__ == "__main__":
    main()
