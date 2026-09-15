# Architecture

## Services

```text
                       +----------------------+
                       | Client / Agent / LLM |
                       +----------+-----------+
                                  |
                                  v
                    +---------------------------+
                    | Unified FastAPI API :8000 |
                    +----+------------------+---+
                         |                  |
             ingestion   |                  | retrieval
                         v                  v
                    +---------+       +-----------+
                    |  Redis  |       | Embedder  |
                    | Celery  |       +-----+-----+
                    +----+----+             |
                         |                  v
                         v              +--------+
                    +---------+         | Qdrant |
                    | Workers |-------->| :6333  |
                    +----+----+         +--------+
                         |
             +-----------+-----------+
             |                       |
             v                       v
       +-----------+            +----------+
       |  Docling  |            | Embedder |
       | parser    |            | dense +  |
       | :8001     |            | sparse   |
       +-----------+            | :8002    |
                                +----------+
```

Only the unified API needs to be exposed to application clients. Qdrant and Redis ports are mapped by default for local debugging and can be removed or firewalled in production.

## Ingestion data flow

```text
HTTP multipart upload
  -> SHA-256 and file-size validation
  -> optional deduplication in Qdrant
  -> Celery queue in Redis
  -> worker
  -> parser-docling
      -> DocumentConverter
      -> selected chunker
  -> embedder
      -> dense vector
      -> sparse BM25 vector
  -> Qdrant upsert
```

## Retrieval data flow

```text
query
  -> query dense embedding + sparse embedding
  -> Qdrant
       dense | sparse | hybrid RRF
  -> optional CrossEncoder reranker
  -> normalized sources/citations
  -> /rag/search OR /rag/context OR /rag/chat
```

## Tenancy

Every indexed point carries `tenant_id`. Every document lookup, delete and search operation applies a mandatory tenant filter. The default tenant header is `X-Tenant-ID`; its name can be configured.

This is logical isolation, not a substitute for physically separated Qdrant clusters when regulatory or adversarial isolation requirements demand it.
