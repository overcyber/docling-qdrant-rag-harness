#!/usr/bin/env python3
"""Detailed end-to-end integration test suite for Docling Qdrant RAG Harness."""

import json
import time
import unittest
import urllib.request
import urllib.error
from pathlib import Path

API_BASE = "http://127.0.0.1:8000"

def make_req(endpoint: str, method: str = "GET", data: dict | bytes = None, headers: dict = None, is_json: bool = True):
    url = f"{API_BASE}{endpoint}"
    req_headers = headers.copy() if headers else {}
    body = None
    if data is not None:
        if isinstance(data, bytes):
            body = data
        elif is_json:
            body = json.dumps(data).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        content = resp.read().decode("utf-8")
        return json.loads(content) if is_json and content else content

def make_multipart_upload(endpoint: str, filename: str, file_bytes: bytes, metadata: dict, proc_opts: dict, tenant: str = "default"):
    boundary = "----TestBoundary" + str(int(time.time() * 1000))
    body = bytearray()

    # metadata
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="metadata"\r\n\r\n')
    body.extend(json.dumps(metadata).encode() + b"\r\n")

    # processing_options
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="processing_options"\r\n\r\n')
    body.extend(json.dumps(proc_opts).encode() + b"\r\n")

    # file
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    body.extend(b"Content-Type: text/markdown\r\n\r\n")
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{API_BASE}{endpoint}",
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Tenant-ID": tenant,
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def wait_for_job(job_id: str, tenant: str = "default", timeout: int = 120):
    start = time.time()
    while time.time() - start < timeout:
        res = make_req(f"/v1/jobs/{job_id}", headers={"X-Tenant-ID": tenant})
        state = res.get("state")
        if state in ("SUCCESS", "FAILURE"):
            return res
        time.sleep(1)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout}s")


class SystemDetailedE2ETests(unittest.TestCase):

    def test_01_health_and_readiness(self):
        """Test health and readiness endpoints."""
        health = make_req("/health")
        self.assertEqual(health.get("status"), "ok")
        self.assertEqual(health.get("service"), "api")

        ready = make_req("/ready")
        self.assertEqual(ready.get("status"), "ready")
        checks = ready.get("checks", {})
        self.assertTrue(checks.get("redis"))
        self.assertTrue(checks.get("qdrant"))
        self.assertTrue(checks.get("parser"))
        self.assertTrue(checks.get("embedder"))

    def test_02_config_endpoints(self):
        """Test configuration retrieval and option validation."""
        cfg = make_req("/v1/config")
        self.assertIn("api", cfg)
        self.assertIn("chunking_defaults", cfg)
        self.assertIn("models", cfg)

        chunkers = make_req("/v1/config/chunkers")
        self.assertIn("hybrid", chunkers["types"])
        self.assertIn("hierarchical", chunkers["types"])
        self.assertIn("line_based", chunkers["types"])

        # Validate options payload
        valid = make_req(
            "/v1/config/processing-options/validate",
            method="POST",
            data={"chunking": {"type": "hybrid", "max_tokens": 200}}
        )
        self.assertTrue(valid.get("valid"))

    def test_03_three_chunking_strategies_ingestion(self):
        """Test ingestion with hybrid, hierarchical, and line_based strategies."""
        tenant = "test-chunking-suite"
        strategies = ["hybrid", "hierarchical", "line_based"]
        doc_content = (
            "# Advanced Cybersecurity Report\n\n"
            "## Threat Intelligence\n"
            "Anomalous traffic was detected correlating with known botnet command and control signatures.\n\n"
            "| Host | Protocol | Anomaly Score |\n"
            "| --- | --- | --- |\n"
            "| 192.168.1.50 | TCP/443 | 0.94 |\n"
            "| 10.0.0.12 | UDP/53 | 0.88 |\n\n"
            "### Mitigation Strategy\n"
            "Deploy deep packet inspection and apply dynamic iptables rules to quarantine infected nodes.\n"
        ).encode("utf-8")

        for strat in strategies:
            filename = f"report_{strat}.md"
            upload = make_multipart_upload(
                "/v1/documents",
                filename,
                doc_content,
                metadata={"strategy_test": strat, "category": "sec_report"},
                proc_opts={"chunking": {"type": strat, "max_tokens": 100}, "deduplicate": False},
                tenant=tenant
            )
            self.assertEqual(upload.get("status"), "queued")
            job_id = upload.get("job_id")
            doc_id = upload.get("document_id")

            job_result = wait_for_job(job_id, tenant=tenant)
            self.assertEqual(job_result.get("state"), "SUCCESS", f"Failed processing with {strat}")
            res = job_result.get("result", {})
            self.assertEqual(res.get("chunker_type"), strat)
            self.assertGreater(res.get("chunks", 0), 0)

            # Check chunk retrieval endpoint
            doc_resp = make_req(f"/v1/documents/{doc_id}", headers={"X-Tenant-ID": tenant})
            self.assertIn("chunks", doc_resp)
            self.assertEqual(len(doc_resp["chunks"]), res.get("chunks"))

    def test_04_rag_retrieval_modes(self):
        """Test hybrid, dense, and sparse search modes."""
        tenant = "test-chunking-suite"
        query = "mitigation dynamic iptables quarantine infected nodes"

        for mode in ("hybrid", "dense", "sparse"):
            search_res = make_req(
                "/v1/rag/search",
                method="POST",
                data={
                    "query": query,
                    "mode": mode,
                    "top_k": 3,
                    "candidate_k": 10
                },
                headers={"X-Tenant-ID": tenant}
            )
            self.assertIn("results", search_res)
            self.assertGreater(len(search_res["results"]), 0, f"No results returned for mode {mode}")
            top_hit = search_res["results"][0]
            self.assertIn("text", top_hit)
            self.assertIn("score", top_hit)
            self.assertIn("citation", top_hit)

    def test_05_metadata_filtering(self):
        """Test metadata filtering capabilities in RAG search."""
        tenant = "test-chunking-suite"
        # Filter matching only the hierarchical document
        search_res = make_req(
            "/v1/rag/search",
            method="POST",
            data={
                "query": "anomalous traffic signatures",
                "mode": "hybrid",
                "top_k": 5,
                "filters": {"strategy_test": "hierarchical"}
            },
            headers={"X-Tenant-ID": tenant}
        )
        self.assertGreater(len(search_res["results"]), 0)
        for r in search_res["results"]:
            self.assertEqual(r.get("chunker_type"), "hierarchical")

    def test_06_rag_context_assembly(self):
        """Test context assembly endpoint for external agents."""
        tenant = "test-chunking-suite"
        context_res = make_req(
            "/v1/rag/context",
            method="POST",
            data={
                "query": "botnet command control signatures",
                "mode": "hybrid",
                "top_k": 2
            },
            headers={"X-Tenant-ID": tenant}
        )
        self.assertIn("context", context_res)
        self.assertIn("sources", context_res)
        self.assertIn("[S1]", context_res["context"])

        # Also verify body aliases (tenant, limit) without X-Tenant-ID header
        alias_res = make_req(
            "/v1/rag/context",
            method="POST",
            data={
                "query": "botnet command control signatures",
                "tenant": tenant,
                "limit": 2
            }
        )
        self.assertIn("context", alias_res)
        self.assertIn("sources", alias_res)
        self.assertEqual(alias_res.get("tenant_id"), tenant)
        self.assertIn("[S1]", alias_res["context"])

    def test_07_tenant_isolation(self):
        """Verify strict multi-tenant data isolation in Qdrant."""
        search_res = make_req(
            "/v1/rag/search",
            method="POST",
            data={
                "query": "Advanced Cybersecurity Report",
                "mode": "hybrid",
                "top_k": 5
            },
            headers={"X-Tenant-ID": "unrelated-tenant-empty"}
        )
        self.assertEqual(len(search_res.get("results", [])), 0, "Tenant isolation leaked documents!")

    def test_08_document_deletion_lifecycle(self):
        """Test deleting a document and ensuring chunks are purged from Qdrant."""
        tenant = "test-deletion-suite"
        upload = make_multipart_upload(
            "/v1/documents",
            "ephemeral_doc.md",
            b"# Ephemeral Data\nThis document will be deleted.\n",
            metadata={"tag": "temporary"},
            proc_opts={"deduplicate": False},
            tenant=tenant
        )
        job_result = wait_for_job(upload["job_id"], tenant=tenant)
        self.assertEqual(job_result.get("state"), "SUCCESS")
        doc_id = upload["document_id"]

        # Verify chunks exist
        doc_before = make_req(f"/v1/documents/{doc_id}", headers={"X-Tenant-ID": tenant})
        self.assertGreater(len(doc_before["chunks"]), 0)

        # Delete document
        del_res = make_req(f"/v1/documents/{doc_id}", method="DELETE", headers={"X-Tenant-ID": tenant})
        self.assertEqual(del_res.get("status"), "deleted")

        # Verify chunks are gone (404 Not Found)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            make_req(f"/v1/documents/{doc_id}", headers={"X-Tenant-ID": tenant})
        self.assertEqual(ctx.exception.code, 404)

    def test_09_deduplication(self):
        """Test deduplication logic preventing duplicate storage in Qdrant."""
        tenant = "test-dedupe-suite"
        run_marker = f"run_{time.time()}"
        content = f"# Deduplication Test Document\nUnique content {run_marker} for testing.\n".encode("utf-8")
        
        # First upload
        up1 = make_multipart_upload(
            "/v1/documents",
            f"dedupe_{run_marker}.md",
            content,
            metadata={"domain": "dedupe", "marker": run_marker},
            proc_opts={"deduplicate": True},
            tenant=tenant
        )
        self.assertEqual(up1["status"], "queued")
        job1 = wait_for_job(up1["job_id"], tenant=tenant)
        self.assertEqual(job1["state"], "SUCCESS")

        # Second upload of exact same content and metadata with deduplicate=True
        up2 = make_multipart_upload(
            "/v1/documents",
            f"dedupe_{run_marker}.md",
            content,
            metadata={"domain": "dedupe", "marker": run_marker},
            proc_opts={"deduplicate": True},
            tenant=tenant
        )
        self.assertEqual(up2["status"], "duplicate")
        self.assertEqual(up2["duplicate_of"], up1["document_id"])
        self.assertIsNone(up2["job_id"])

    def test_10_rag_chat_retrieval_mode(self):
        """Test RAG chat endpoint operating in retrieval-only mode and tracking conversation memory."""
        tenant = "test-chunking-suite"
        chat_res = make_req(
            "/v1/rag/chat",
            method="POST",
            data={
                "question": "What is the mitigation strategy for infected nodes?",
                "conversation_id": "test-conv-001",
                "retrieval": {"mode": "hybrid", "top_k": 2}
            },
            headers={"X-Tenant-ID": tenant}
        )
        self.assertEqual(chat_res.get("mode"), "retrieval_only")
        self.assertEqual(chat_res.get("conversation_id"), "test-conv-001")
        self.assertGreater(len(chat_res.get("sources", [])), 0)
        self.assertIn("prepared_prompt", chat_res)

    def test_11_batch_upload(self):
        """Test batch upload endpoint /v1/documents/batch."""
        tenant = "test-batch-suite"
        boundary = "----BatchTestBoundary" + str(int(time.time() * 1000))
        body = bytearray()

        # processing_options
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="processing_options"\r\n\r\n')
        body.extend(json.dumps({"deduplicate": False}).encode() + b"\r\n")

        # file 1
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="files"; filename="batch1.md"\r\n')
        body.extend(b"Content-Type: text/markdown\r\n\r\n")
        body.extend(b"# Batch File 1\nFirst document in batch ingestion.\n\r\n")

        # file 2
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="files"; filename="batch2.md"\r\n')
        body.extend(b"Content-Type: text/markdown\r\n\r\n")
        body.extend(b"# Batch File 2\nSecond document in batch ingestion.\n\r\n")

        body.extend(f"--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            f"{API_BASE}/v1/documents/batch",
            data=bytes(body),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-Tenant-ID": tenant,
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        self.assertEqual(data.get("count"), 2)
        jobs = data.get("jobs", [])
        self.assertEqual(len(jobs), 2)
        for j in jobs:
            res = wait_for_job(j["job_id"], tenant=tenant)
            self.assertEqual(res["state"], "SUCCESS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
