# Validation status

Version: `2.0.0`

## Completed in the build environment

- Python syntax compilation for all microservices;
- Pydantic schema tests for all three chunkers and all three retrieval modes;
- Docker Compose YAML parse and structural checks;
- MkDocs YAML/navigation target validation;
- Google Colab notebook JSON and Python code-cell syntax validation;
- shell syntax validation for validation/smoke scripts;
- local Markdown link validation;
- stale endpoint/default checks (`8003`, old 420-token default);
- ZIP integrity and SHA-256 are produced during final packaging.

## Runtime integration

This build environment does not expose a Docker/Podman daemon, so the full container stack cannot be launched here. After extraction, run:

```bash
cp .env.example .env
make up
make smoke
```

The smoke test performs liveness/readiness checks, uploads a document, waits for the asynchronous Celery job and executes hybrid RAG retrieval.
