# Docling Qdrant Advanced RAG Harness

This project is a reusable **document RAG agent harness**. It separates parsing, asynchronous orchestration, embeddings and vector storage into independent services while exposing a **single public FastAPI API** for ingestion and retrieval.

## Goals

- process many documents without blocking HTTP requests;
- preserve document structure and provenance with Docling;
- allow runtime selection of three Docling chunking strategies;
- combine dense semantic retrieval and sparse lexical retrieval;
- isolate tenants in the same Qdrant collection;
- serve chatbots and agents through a stable API contract;
- operate with or without an attached LLM;
- support local Docker deployment and a Google Colab demonstration.

## Public endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness |
| `GET /ready` | dependency readiness |
| `GET /v1/config` | effective non-secret configuration |
| `GET /v1/config/chunkers` | chunker capabilities/examples |
| `POST /v1/documents` | asynchronous single-document ingestion |
| `POST /v1/documents/batch` | asynchronous batch ingestion |
| `GET /v1/jobs/{job_id}` | job state/progress |
| `GET /v1/documents/{document_id}` | inspect indexed chunks |
| `DELETE /v1/documents/{document_id}` | delete document |
| `POST /v1/rag/search` | retrieve chunks |
| `POST /v1/rag/context` | return evidence block for an external agent |
| `POST /v1/rag/chat` | retrieval plus optional LLM generation |

The compatibility aliases `/v1/search`, `/v1/context` and `/v1/chat` remain available but are intentionally hidden from OpenAPI.
