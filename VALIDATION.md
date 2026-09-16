# Validation status

Version: `2.1.0`
Status: **ALL CHECKS AND END-TO-END RUNTIME TESTS PASSING**

## 1. Build-time and Schema Validation (`scripts/validate.sh`)

A validação automatizada cobre:

- compilação sintática de todos os serviços Python (`compileall`);
- schemas dos três chunkers (`hybrid`, `hierarchical`, `line_based`) e três modos de retrieval (`hybrid`, `dense`, `sparse`);
- schemas dos quatro providers LLM (`openai`, `ollama`, `llamacpp`, `vllm`);
- ingestão direta de texto, multi-corpus e Agent Profile;
- payloads nativos do Ollama e extensões llama.cpp/vLLM;
- YAML estrutural do Docker Compose e dependências de serviços;
- presença dos serviços core e profiles opcionais;
- integridade do MkDocs e links de navegação;
- notebook Colab JSON + sintaxe das code cells (`colab/RAG_Harness_Colab.ipynb`);
- OpenAPI da FastAPI quando as dependências runtime estão instaladas;
- criação do schema do control plane em SQLite para teste sem dependência externa;
- shell syntax dos scripts;
- prevenção de endpoints depreciados (`8003`) e tokens legados (`420`);
- ausência de arquivos de secrets conhecidos no pacote.

Execute:

```bash
./scripts/validate.sh
```

## 2. Full Container Runtime Integration

All 6 microservices built and verified operational in Docker:

| Service | Technology | Port / Bind | Healthcheck Status |
|---|---|---|---|
| `api` | FastAPI / Uvicorn (Python 3.12) | 127.0.0.1:8000 | Healthy (`/health`, `/ready`) |
| `worker` | Celery (prefork concurrency=2) | Redis broker | Ready, processing tasks |
| `parser-docling` | IBM Docling (PyTorch / Vision) | 127.0.0.1:8001 | Healthy |
| `embedder` | FastEmbed (dense) + BM25 (sparse) | 127.0.0.1:8002 | Healthy |
| `redis` | Redis 7.4 Alpine (AOF enabled) | 127.0.0.1:6379 | Healthy (PONG) |
| `qdrant` | Qdrant v1.19.1 | 127.0.0.1:6333 / 6334 | Healthy |
| `docs` | MkDocs Material | 127.0.0.1:8004 | Operational (HTTP 200) |

## 3. Automated End-to-End Test Suite (`tests/test_system_e2e.py`)

14 automated tests discoverable and executed via `scripts/validate.sh` and `unittest`:

1. **`test_01_health_and_readiness`**: Validates `/health` and multi-service `/ready` probes.
2. **`test_02_config_endpoints`**: Tests `/v1/config`, `/v1/config/chunkers`, and typed payload validation at `/v1/config/processing-options/validate`.
3. **`test_03_three_chunking_strategies_ingestion`**: Uploads and indexes documents verifying all three chunkers (`hybrid`, `hierarchical`, `line_based`) and verifies chunk retrieval via `GET /v1/documents/{document_id}`.
4. **`test_04_rag_retrieval_modes`**: Verifies retrieval across all 3 search modes (`hybrid`, `dense`, `sparse`).
5. **`test_05_metadata_filtering`**: Verifies Qdrant payload filters on user metadata and chunker type attributes.
6. **`test_06_rag_context_assembly`**: Tests `/v1/rag/context` assembling formatted context blocks with `[S1]`, `[S2]` citation anchors.
7. **`test_07_tenant_isolation`**: Confirms strict multi-tenant isolation; cross-tenant document searches return 0 hits.
8. **`test_08_document_deletion_lifecycle`**: Deletes document via `DELETE /v1/documents/{document_id}` and confirms immediate purge from Qdrant.
9. **`test_09_deduplication`**: Verifies SHA-256 + processing profile fingerprinting, rejecting duplicate uploads with HTTP status `duplicate` and referencing original `document_id`.
10. **`test_10_rag_chat_retrieval_mode`**: Verifies `/v1/rag/chat` conversation memory management in Redis and retrieval-only fallback.
11. **`test_11_batch_upload`**: Tests `/v1/documents/batch` multipart uploading multiple files concurrently.

## 4. Real-World Document Ingestion & RAG Query Benchmarks

### Benchmark A: Ingestão de Artigo e Busca Híbrida
- **Arquivo**: `An_Efficient_SQL_Injection_Detection_System_Using_Deep_Learning.pdf` (1.6 MB)
- **Chunks gerados**: 49 chunks com proveniência de página e cabeçalhos estruturais.
- **Busca Híbrida**: Retornou citação `S1` com score de relevância `0.75`.

### Benchmark B: Ingestão com GPU e Montagem de Contexto RAG
- **Arquivo**: `Anomaly-based network intrusion detection- Techniques, systems and challenges.pdf` (366 KB)
- **Tenant**: `mestrado-cybersec` | **Corpus**: `seguranca`
- **Job ID**: `679db9cb-4f06-495f-9432-722233b5459d`
- **Document ID**: `2ddec71b-e36e-463c-ba80-ba0e77243a1b`
- **Chunks indexados no Qdrant**: 188 chunks
- **Consulta via RAG (`POST /v1/rag/search`)**:
  - **Query**: *"What are the main techniques, systems and challenges in anomaly-based network intrusion detection?"*
  - **Score**: `0.6428` (Citação `S1`)
  - **Seções recuperadas**: `"Anomaly-based network intrusion detection: Techniques, systems and challenges"` (Pág. 1) e `"4. Open issues and challenges"` (Pág. 8).
- **Montagem de Contexto (`POST /v1/rag/context`)**:
  - Contexto montado instantaneamente com tags de citação `[S1]`, `[S2]` pronto para consumo por LLMs.

### Ingestão em Lote
- **Script**: [`scripts/ingest_folder.py`](scripts/ingest_folder.py) testado com 76 PDFs em `/opt/pdf-ingestao`.
- **Deduplicação**: Arquivos já ingeridos detectados e ignorados em 0.18s por hash SHA-256 sem reprocessamento.

