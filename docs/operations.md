# Operations

## Scaling workers

```bash
docker compose up -d --scale worker=4
```

Parsing/OCR is normally the most expensive stage. Scale workers gradually and observe RAM usage because each active Docling conversion may load models and large document structures.

## Celery behavior

The worker uses:

- late acknowledgements;
- `task_reject_on_worker_lost`;
- prefetch multiplier `1`;
- configurable process recycling with `WORKER_MAX_TASKS_PER_CHILD`.

These settings are appropriate for long document-processing tasks and reduce the chance that one worker reserves many large jobs.

## Monitoring

Start Flower:

```bash
docker compose --profile monitoring up -d flower
```

Default UI:

```text
http://localhost:5555
```

## Persistence

Named volumes:

- `qdrant_data` — vector database;
- `redis_data` — Redis AOF data;
- `uploads` — retained uploaded files;
- `hf_models` — Docling/Hugging Face model cache;
- `fastembed_models` — FastEmbed cache.

Back up Qdrant according to your production Qdrant deployment strategy. Docker volume copies are acceptable for development but are not a substitute for application-consistent snapshots in production.

## Readiness

`GET /ready` checks Redis, Qdrant, parser and embedder. Use it for deployment readiness; use `/health` only for liveness.


## Job retention

Celery task results and tenant/job ownership mappings default to seven days (`CELERY_RESULT_EXPIRES=604800`, `JOB_OWNER_TTL_SECONDS=604800`). Increase both together if ingestion jobs/results must remain inspectable longer.


## In-flight deduplication

When deduplication is enabled, the API first checks Qdrant for an indexed equivalent and then acquires an atomic Redis reservation keyed by tenant plus ingestion fingerprint. A concurrent equivalent upload returns `duplicate_pending` instead of creating a second Celery job. The reservation is released on successful indexing or terminal task failure and also has a safety TTL (`DEDUPE_PENDING_TTL_SECONDS`, default 7200 seconds).


## Embedding-space guard

Each newly indexed point records the dense model, sparse model and BM25 language. Before indexing or retrieval, the harness compares the active embedder identity with an existing point in the collection and rejects incompatible spaces even when vector dimensions are equal. A model migration therefore requires a new `QDRANT_COLLECTION` or a full reindex.

## CI

`.github/workflows/validate.yml` runs a lightweight validation on pushes and pull requests. It checks Python syntax, Pydantic request schemas, MkDocs navigation targets, Colab code-cell syntax and `docker compose config`. It intentionally does not download Docling/FastEmbed models or execute OCR in CI; use `scripts/smoke_test.sh` against a built stack for integration validation.
