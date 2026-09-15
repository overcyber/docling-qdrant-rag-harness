# cURL examples

Assume:

```bash
export API=http://localhost:8000
export TENANT=demo
```

If `API_KEY` is configured:

```bash
export AUTH='Authorization: Bearer YOUR_KEY'
```

## Inspect effective configuration

```bash
curl -H "X-Tenant-ID: $TENANT" "$API/v1/config"
curl -H "X-Tenant-ID: $TENANT" "$API/v1/config/chunkers"
```

## Hybrid ingestion

```bash
curl -X POST "$API/v1/documents" \
  -H "X-Tenant-ID: $TENANT" \
  -F 'file=@examples/sample.md' \
  -F 'metadata={"project":"demo"}' \
  -F 'processing_options={"chunking":{"type":"hybrid","max_tokens":120,"merge_peers":true}}'
```

## Hierarchical ingestion

```bash
curl -X POST "$API/v1/documents" \
  -H "X-Tenant-ID: $TENANT" \
  -F 'file=@examples/sample.md' \
  -F 'processing_options={"chunking":{"type":"hierarchical","always_emit_headings":false}}'
```

## Line-based ingestion

```bash
curl -X POST "$API/v1/documents" \
  -H "X-Tenant-ID: $TENANT" \
  -F 'file=@examples/sample.md' \
  -F 'processing_options={"chunking":{"type":"line_based","max_tokens":120,"omit_prefix_on_overflow":true}}'
```

## Search

```bash
curl -X POST "$API/v1/rag/search" \
  -H 'Content-Type: application/json' \
  -H "X-Tenant-ID: $TENANT" \
  -d '{"query":"advanced RAG","mode":"hybrid","top_k":5,"candidate_k":20}'
```

## Context for an external agent

```bash
curl -X POST "$API/v1/rag/context" \
  -H 'Content-Type: application/json' \
  -H "X-Tenant-ID: $TENANT" \
  -d '{"query":"advanced RAG","top_k":5}'
```

## Chat

```bash
curl -X POST "$API/v1/rag/chat" \
  -H 'Content-Type: application/json' \
  -H "X-Tenant-ID: $TENANT" \
  -d '{"question":"Explain the architecture and cite the evidence."}'
```
