# Configuration

Configuration is environment-driven. Copy `.env.example` to `.env` and change only what is needed.

## FastAPI / HTTP

| Variable | Default | Purpose |
|---|---|---|
| `API_TITLE` | Docling Qdrant Advanced RAG Harness | OpenAPI/UI title |
| `API_DESCRIPTION` | built-in description | OpenAPI description |
| `API_VERSION` | `2.0.0` | API version |
| `API_DOCS_ENABLED` | `true` | enable Swagger/ReDoc/OpenAPI routes |
| `API_DOCS_URL` | `/docs` | Swagger path |
| `API_REDOC_URL` | `/redoc` | ReDoc path |
| `API_OPENAPI_URL` | `/openapi.json` | OpenAPI JSON path |
| `API_ROOT_PATH` | empty | reverse-proxy root path |
| `API_PUBLIC_BASE_URL` | empty | OpenAPI server base URL |
| `API_ALLOWED_HOSTS` | `*` | TrustedHost allowlist |
| `API_CORS_ORIGINS` | `*` | CORS origins |
| `API_CORS_ALLOW_CREDENTIALS` | `false` | credentialed CORS |
| `API_CORS_ALLOW_METHODS` | GET,POST,DELETE,OPTIONS | CORS methods |
| `API_CORS_ALLOW_HEADERS` | `*` | CORS request headers |
| `API_WORKERS` | `2` | Uvicorn workers |
| `API_KEEP_ALIVE` | `5` | keep-alive seconds |
| `API_LOG_LEVEL` | `info` | Uvicorn log level |
| `API_MAX_BATCH_FILES` | `100` | max files per batch request |
| `API_UPLOAD_BUFFER_MB` | `1` | streaming upload read size |
| `API_BIND_HOST` | `127.0.0.1` | host interface exposed by Docker Compose |

For public deployment, do not leave `API_CORS_ORIGINS=*` or `API_ALLOWED_HOSTS=*` unless that exposure is intentional.

## Docker host exposure

Host-exposed services bind to loopback by default: `API_BIND_HOST`, `REDIS_BIND_HOST`, `QDRANT_BIND_HOST`, `DOCS_BIND_HOST` and `FLOWER_BIND_HOST` are `127.0.0.1`. Set a bind host to `0.0.0.0` only when remote access is intentional and protected by firewall/reverse proxy/authentication.

## Security and tenancy

| Variable | Default |
|---|---|
| `API_KEY` | empty/disabled |
| `TENANT_HEADER_NAME` | `X-Tenant-ID` |
| `DEFAULT_TENANT_ID` | `default` |
| `JOB_OWNER_TTL_SECONDS` | `604800` | tenant ownership record retention for async jobs |
| `DEDUPE_PENDING_TTL_SECONDS` | `7200` | Redis reservation for equivalent queued/in-flight ingestion |

## Chunking

| Variable | Default |
|---|---|
| `CHUNKER_TYPE` | `hybrid` |
| `CHUNK_TOKENIZER_MODEL` | multilingual MiniLM |
| `CHUNK_MAX_TOKENS` | `120` |
| `CHUNK_HYBRID_MERGE_PEERS` | `true` |
| `CHUNK_HYBRID_REPEAT_TABLE_HEADER` | `true` |
| `CHUNK_HYBRID_OMIT_HEADER_ON_OVERFLOW` | `false` |
| `CHUNK_HYBRID_ALWAYS_EMIT_HEADINGS` | `false` |
| `CHUNK_HIERARCHICAL_MERGE_LIST_ITEMS` | `true` |
| `CHUNK_HIERARCHICAL_ALWAYS_EMIT_HEADINGS` | `false` |
| `CHUNK_LINE_PREFIX` | empty |
| `CHUNK_LINE_OMIT_PREFIX_ON_OVERFLOW` | `false` |

## Docling conversion

| Variable | Default |
|---|---|
| `PDF_DO_OCR` | `true` |
| `PDF_DO_TABLE_STRUCTURE` | `true` |
| `PDF_DO_CELL_MATCHING` | `true` |
| `DOCLING_MAX_NUM_PAGES` | `1000` |
| `PARSER_FULL_DOCLING_METADATA` | `false` |
| `MAX_FILE_MB` | `100` |

`PARSER_FULL_DOCLING_METADATA=false` is intentional for scale: full Docling metadata can be large, especially with line-based chunking. The parser still emits headings, pages, item counts and labels needed by normal RAG use.

## Retrieval

| Variable | Default |
|---|---|
| `RETRIEVAL_MODE` | `hybrid` |
| `DEFAULT_TOP_K` | `8` |
| `DEFAULT_CANDIDATE_K` | `40` |
| `MAX_TOP_K` | `50` |
| `MAX_CANDIDATE_K` | `200` |
| `DEFAULT_SCORE_THRESHOLD` | disabled |
| `RERANKER_ENABLED` | `false` |
| `MAX_CONTEXT_CHARS` | `60000` |

Score values are not directly comparable across dense cosine, sparse retrieval and RRF fusion. Calibrate `DEFAULT_SCORE_THRESHOLD` for the chosen mode before enabling it globally.

## Qdrant metadata indexes

Use:

```env
QDRANT_METADATA_INDEX_FIELDS=department,classification,project
```

The harness will create keyword payload indexes for `user_metadata.department`, etc. Unindexed filters still function but can become expensive on large collections.

## LLM

```env
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen3:8b
LLM_API_KEY=
```

Any OpenAI-compatible `/chat/completions` endpoint can be used.


## Queue/result retention

| Variable | Default |
|---|---:|
| `CELERY_VISIBILITY_TIMEOUT` | `7200` | broker visibility timeout for long jobs |
| `CELERY_RESULT_EXPIRES` | `604800` | Celery result retention in seconds |
| `JOB_OWNER_TTL_SECONDS` | `604800` | tenant/job ownership retention |
| `DEDUPE_PENDING_TTL_SECONDS` | `7200` | in-flight deduplication reservation |

Keep `JOB_OWNER_TTL_SECONDS >= CELERY_RESULT_EXPIRES` so a result is never queryable after its tenant ownership record has expired.

## Embedding model changes

The Qdrant dense vector dimension is inferred from the first produced embedding when the collection is created. `EMBEDDING_DIM` remains only as a fallback. The harness also stores `embedding_models` (`dense`, `sparse`, `bm25_language`) in indexed payloads and rejects a later ingestion/query when that identity conflicts with the existing collection. This catches incompatible 384→384 model changes that a dimension check alone cannot detect.

If you switch `DENSE_MODEL`, `SPARSE_MODEL` or `BM25_LANGUAGE` after a collection already contains vectors, use a new `QDRANT_COLLECTION` or rebuild/reindex the collection; vectors/sparse weights from different retrieval spaces must never be mixed. Collections created by older harness versions without `embedding_models` metadata should be reindexed before relying on this guard.

Also align `CHUNK_TOKENIZER_MODEL` and `CHUNK_MAX_TOKENS` with the actual dense-model input window. The supplied MiniLM multilingual default uses a conservative `120`-token chunk budget because the upstream Sentence Transformers model is configured for 128 tokens.
