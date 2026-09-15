#!/usr/bin/env bash
set -euo pipefail
API="${API:-http://localhost:8000}"
TENANT="${TENANT:-smoke-test}"
CORPUS="${CORPUS:-smoke-corpus}"
AUTH=()
if [[ -n "${API_KEY:-}" ]]; then AUTH=(-H "Authorization: Bearer ${API_KEY}"); fi
curl -fsS "$API/health" | python -m json.tool
curl -fsS "$API/ready" | python -m json.tool
curl -fsS "${AUTH[@]}" "$API/v1/config/chunkers" | python -m json.tool
curl -fsS "${AUTH[@]}" "$API/v1/llm/providers" | python -m json.tool
RESP=$(curl -fsS -X POST "$API/v1/documents/text" "${AUTH[@]}" -H "X-Tenant-ID: $TENANT" -H 'Content-Type: application/json' -d "{\"title\":\"Smoke note\",\"text\":\"The Docling Qdrant harness supports direct text ingestion, hybrid retrieval and logical corpora.\",\"corpus_id\":\"$CORPUS\",\"metadata\":{\"suite\":\"smoke\"},\"processing_options\":{\"chunking\":{\"type\":\"hybrid\",\"max_tokens\":120},\"deduplicate\":false}}")
echo "$RESP" | python -m json.tool
JOB_ID=$(python -c 'import json,sys; print(json.load(sys.stdin).get("job_id") or "")' <<<"$RESP")
[[ -n "$JOB_ID" ]] || { echo 'No job_id returned' >&2; exit 1; }
DONE=0
for _ in $(seq 1 120); do
  JOB=$(curl -fsS "${AUTH[@]}" -H "X-Tenant-ID: $TENANT" "$API/v1/jobs/$JOB_ID")
  STATE=$(python -c 'import json,sys; print(json.load(sys.stdin)["state"])' <<<"$JOB")
  echo "state=$STATE"
  if [[ "$STATE" == "SUCCESS" ]]; then echo "$JOB" | python -m json.tool; DONE=1; break; fi
  if [[ "$STATE" == "FAILURE" ]]; then echo "$JOB" | python -m json.tool; exit 1; fi
  sleep 2
done
[[ "$DONE" == "1" ]] || { echo "Timed out waiting for ingestion job $JOB_ID" >&2; exit 1; }
curl -fsS -X POST "$API/v1/rag/search" "${AUTH[@]}" -H "X-Tenant-ID: $TENANT" -H 'Content-Type: application/json' -d "{\"query\":\"What capabilities does the harness support?\",\"mode\":\"hybrid\",\"corpora\":[\"$CORPUS\"],\"top_k\":3,\"candidate_k\":10}" | python -m json.tool
