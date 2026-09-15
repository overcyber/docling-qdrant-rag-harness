# Docling Qdrant Advanced RAG Harness

Microservice harness for high-volume document ingestion and advanced Retrieval-Augmented Generation (RAG) using **Docling**, **Qdrant**, **Redis**, **Celery** and a single public **FastAPI** API.

The public API serves both sides of the lifecycle:

- document ingestion and indexing;
- asynchronous job status;
- dense, sparse and hybrid search;
- evidence/context assembly for external agents;
- optional RAG chat through any OpenAI-compatible LLM endpoint;
- embedding-space identity guard to prevent mixing incompatible dense/sparse models.

## Main architecture

```text
Client / Chatbot / Agent
          |
          v
+---------------------------+
| Unified FastAPI API :8000 |
| /v1/documents             |
| /v1/rag/search            |
| /v1/rag/context           |
| /v1/rag/chat              |
+------+--------------------+
       |
       +--> Redis/Celery --> Worker --> Docling parser
       |                         |          |
       |                         |          +--> HybridChunker
       |                         |          +--> HierarchicalChunker
       |                         |          +--> LineBasedTokenChunker
       |                         |
       |                         +--> Embedder --> Qdrant
       |
       +--> Embedder --> Qdrant --> retrieval/RRF/rerank
       |
       +--> Redis conversation memory
```

## Supported input

- PDF
- DOCX
- TXT
- Markdown (`.md`, `.markdown`)

## Three chunking strategies

The chunker can be selected globally through `.env` or overridden **per upload**. Deduplication is processing-aware and protected against concurrent duplicate uploads with an in-flight Redis reservation, so the same document can be indexed with different chunkers without collision:

1. `hybrid` — default; hierarchy-aware and tokenizer-aware split/merge.
2. `hierarchical` — preserves document structural elements and hierarchy.
3. `line_based` — token-aware but line-preserving; useful for tables, code and logs.

See [docs/chunking.md](docs/chunking.md).

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
```

Check:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

The complete typed `ProcessingOptions` schema can also be validated at `POST /v1/config/processing-options/validate`; this makes all three chunker variants visible directly in OpenAPI.

Interactive API documentation:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

Standalone documentation site:

```bash
docker compose --profile documentation up -d docs
```

Then open `http://localhost:8004`.

## Example ingestion

```bash
curl -X POST http://localhost:8000/v1/documents \
  -H 'X-Tenant-ID: lab' \
  -F 'file=@report.pdf' \
  -F 'metadata={"project":"alpha","classification":"internal"}' \
  -F 'processing_options={"chunking":{"type":"hybrid","max_tokens":120},"pdf":{"do_ocr":true,"do_table_structure":true}}'
```

The request returns HTTP `202` with `document_id` and `job_id`.

```bash
curl -H 'X-Tenant-ID: lab' http://localhost:8000/v1/jobs/JOB_ID
```

## Example RAG search

```bash
curl -X POST http://localhost:8000/v1/rag/search \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: lab' \
  -d '{
    "query": "Qual metodologia o relatório utiliza?",
    "mode": "hybrid",
    "top_k": 8,
    "candidate_k": 40,
    "rerank": false,
    "filters": {"project":"alpha", "chunker_type":"hybrid"}
  }'
```

Built-in retrieval filters include `filename`, `sha256`, `document_id`, `chunker_type` and `ingest_fingerprint`; any other key is resolved under `user_metadata.<key>`.

## Documentation

- [Quick start](docs/quickstart.md)
- [Architecture](docs/architecture.md)
- [API guide](docs/api.md)
- [Chunking](docs/chunking.md)
- [Configuration](docs/configuration.md)
- [Agent integration](docs/agent-integration.md)
- [Google Colab](docs/colab.md)
- [Operations](docs/operations.md)
- [Security](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Validation status](VALIDATION.md)

## Validation

Run:

```bash
./scripts/validate.sh
```

After containers are up:

```bash
./scripts/smoke_test.sh
```

## Publicação no GitHub

O repositório de destino é `overcyber/docling-qdrant-rag-harness`. A publicação manual também pode ser feita com:

```bash
./scripts/publish_github.sh git@github.com:overcyber/docling-qdrant-rag-harness.git
```

Ou por HTTPS:

```bash
./scripts/publish_github.sh https://github.com/overcyber/docling-qdrant-rag-harness.git
```

O script inicializa Git quando necessário, usa `main`, impede o staging de `.env`, chaves `.pem/.key` e chaves SSH comuns, cria o commit e faz o push.
