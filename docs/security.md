# Security

## Minimum production changes

1. Configure `API_KEY` or place the API behind an authenticated gateway.
2. Restrict `API_ALLOWED_HOSTS`.
3. Restrict `API_CORS_ORIGINS`.
4. Keep the default loopback binds for Redis and Qdrant unless remote access is required.
5. Do not expose Redis directly to untrusted networks.
6. Do not expose Qdrant directly unless it has network/auth controls appropriate to the environment.
7. Terminate TLS at a reverse proxy or ingress.
8. Set file-size and page-count limits according to available resources.
9. Treat parsed document content as untrusted.

## Multi-tenancy

`tenant_id` filtering is applied to search, document inspection, deletion and deduplication. Async job status is also bound to its tenant in Redis, and mismatched tenants receive `404`. This prevents accidental cross-tenant retrieval/status disclosure at the application layer.

It is not equivalent to cryptographic or physical tenant isolation. For mutually hostile tenants or strict regulatory boundaries, separate collections or Qdrant deployments may be preferable.

## Denial-of-service considerations

Large PDFs, OCR-heavy scans and malformed documents can consume significant CPU/RAM. Controls already included:

- `MAX_FILE_MB`;
- `DOCLING_MAX_NUM_PAGES`;
- asynchronous queueing;
- bounded Celery worker concurrency;
- low Celery prefetch;
- worker process recycling.

A public deployment should additionally use reverse-proxy request limits and rate limiting.

## Secrets

Never commit `.env` with real API keys. The repository includes `.env.example`; use Docker secrets, Kubernetes secrets or a dedicated secret manager for production.
