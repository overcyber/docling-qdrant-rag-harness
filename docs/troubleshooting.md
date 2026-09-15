# Troubleshooting

## `/ready` returns 503

Inspect:

```bash
docker compose ps
docker compose logs --tail=200 api worker parser-docling embedder qdrant redis
```

The readiness response identifies which dependency failed.

## First ingestion is slow

Expected on a new installation. Docling, transformers and FastEmbed may download/cache models on first use.

## OCR consumes too much memory

Try:

```env
PDF_DO_OCR=false
WORKER_CONCURRENCY=1
```

or disable OCR per upload:

```json
{"pdf":{"do_ocr":false}}
```

## Retrieval returns semantically related but misses exact identifiers

Use `mode="hybrid"` or `mode="sparse"`. Sparse retrieval is useful for CVEs, hostnames, serial numbers, acronyms and exact technical terms.

## Too many tiny chunks

For general documents use `hybrid` and keep `merge_peers=true`. Increase `max_tokens` if the embedding model supports the larger window.

## Line-based pages look broad

This is expected. The API reports `page_provenance="document"` for line-based chunks because Docling's line chunker serializes the whole document before splitting lines. Use hybrid/hierarchical when precise page provenance is a primary requirement.
