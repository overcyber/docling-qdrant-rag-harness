# Quick start

## Requirements

- Docker Engine with Docker Compose v2;
- at least 8 GB RAM recommended for comfortable local use;
- internet access on the first build/model download;
- additional RAM/VRAM depending on embedding, OCR and reranker models.

## Start

```bash
cp .env.example .env
docker compose up -d --build
```

Inspect:

```bash
docker compose ps
docker compose logs -f api worker parser-docling embedder
```

Liveness and readiness:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

## Documentation UI

FastAPI:

```text
http://localhost:8000/docs
http://localhost:8000/redoc
```

MkDocs:

```bash
docker compose --profile documentation up -d docs
```

```text
http://localhost:8004
```

## Minimal ingestion

```bash
curl -X POST http://localhost:8000/v1/documents \
  -H 'X-Tenant-ID: demo' \
  -F 'file=@examples/sample.md'
```

Query the returned job:

```bash
curl -H 'X-Tenant-ID: demo' http://localhost:8000/v1/jobs/<job_id>
```

## Minimal retrieval

```bash
curl -X POST http://localhost:8000/v1/rag/search \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: demo' \
  -d '{"query":"What is this document about?","top_k":5}'
```


## Network exposure

The Compose stack binds public host ports to `127.0.0.1` by default. For a remote server, prefer a TLS reverse proxy in front of the API. If direct host exposure is necessary, set `API_BIND_HOST=0.0.0.0` and configure `API_KEY`, `API_ALLOWED_HOSTS`, firewall rules and CORS deliberately.
