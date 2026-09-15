# API guide

The public interface is a single FastAPI service on port `8000`.

## Authentication

When `API_KEY` is empty, authentication is disabled for local use.

When configured, either form is accepted:

```http
Authorization: Bearer <API_KEY>
```

or:

```http
X-API-Key: <API_KEY>
```

## Tenant selection

Default:

```http
X-Tenant-ID: project-a
```

The header name can be changed with `TENANT_HEADER_NAME`.

## Ingest one document

`POST /v1/documents`

Multipart fields:

| Field | Required | Description |
|---|---:|---|
| `file` | yes | PDF, DOCX, TXT, MD, MARKDOWN |
| `metadata` | no | arbitrary JSON object stored with every chunk |
| `processing_options` | no | Docling/chunking/conversion JSON object |

Response:

```json
{
  "document_id": "...",
  "job_id": "...",
  "sha256": "...",
  "filename": "manual.pdf",
  "bytes": 123456,
  "status": "queued"
}
```

Deduplication is based on an ingestion fingerprint containing the source SHA-256, effective processing profile and user metadata. Therefore the same PDF can be indexed independently with `hybrid`, `hierarchical` and `line_based`; only an exact equivalent ingestion is considered a duplicate.

An already indexed duplicate can return:

```json
{
  "document_id": "existing-document-id",
  "job_id": null,
  "status": "duplicate",
  "duplicate_of": "existing-document-id"
}
```

If an equivalent ingestion is still queued or processing, Redis provides an atomic pending reservation and the response uses `status="duplicate_pending"` with the original `document_id`/`job_id`. The reservation TTL is controlled by `DEDUPE_PENDING_TTL_SECONDS`.

## Validate processing options / OpenAPI schema

`POST /v1/config/processing-options/validate` accepts a normal JSON `ProcessingOptions` body. Besides validation, this route makes the full discriminated union for all three chunkers visible in Swagger/OpenAPI, while `/v1/documents` remains multipart because it carries a file.

## Batch ingestion

`POST /v1/documents/batch`

The same metadata and processing options apply to every file in that multipart request. The maximum number of files is configured by `API_MAX_BATCH_FILES`.

## Job status

`GET /v1/jobs/{job_id}`

Possible Celery states include `PENDING`, `STARTED`, `PROGRESS`, `SUCCESS` and `FAILURE`. Job ownership is tenant-scoped; another tenant receives `404` rather than job metadata.

During processing the `progress` body contains stages such as `parsing`, `embedding` and `indexing`.

## Inspect document

`GET /v1/documents/{document_id}?limit=100`

Returns chunk text, headings, page information, selected chunker and metadata.

## Delete document

`DELETE /v1/documents/{document_id}`

Deletes points from Qdrant and any retained source file in the tenant upload directory.

## Search

`POST /v1/rag/search`

```json
{
  "query": "What does the policy require?",
  "mode": "hybrid",
  "top_k": 8,
  "candidate_k": 40,
  "score_threshold": null,
  "filters": {
    "department": "security"
  },
  "rerank": true,
  "include_contextualized_text": true
}
```

Retrieval modes:

- `hybrid`: dense + sparse with Qdrant RRF fusion;
- `dense`: semantic embedding only;
- `sparse`: lexical BM25-style sparse retrieval only.

## Build agent context

`POST /v1/rag/context`

Uses the same request schema as search and returns both structured sources and a concatenated evidence block containing source tags `[S1]`, `[S2]`, etc.

This endpoint is intended for an external agent that already owns its LLM and orchestration loop.

## RAG chat

`POST /v1/rag/chat`

```json
{
  "question": "Summarize the incident findings.",
  "conversation_id": "optional-stable-id",
  "mode": "hybrid",
  "top_k": 8,
  "candidate_k": 40,
  "filters": {},
  "rerank": false
}
```

If `LLM_BASE_URL` and `LLM_MODEL` are configured, the API calls an OpenAI-compatible `/chat/completions` endpoint.

If no LLM is configured, the endpoint remains useful: it returns `prepared_prompt` and retrieved sources so the caller can perform generation elsewhere.


## Retrieval filters

Built-in filter keys are `filename`, `sha256`, `document_id`, `chunker_type` and `ingest_fingerprint`. Any other key supplied in `filters` is resolved as `user_metadata.<key>`. Lists use Qdrant `MatchAny` semantics. Tenant isolation is always injected server-side and cannot be overridden by the request.


## Retrieval configuration conflicts

If the active embedding service does not match the embedding-space identity already stored in the Qdrant collection, RAG retrieval returns HTTP `409` instead of issuing a mathematically invalid similarity search. Use a new collection or reindex after changing embedding/sparse models.
