#!/usr/bin/env bash
set -euo pipefail

API="${API:-http://localhost:8000}"
TENANT="${TENANT:-smoke-test}"
AUTH=()
if [[ -n "${API_KEY:-}" ]]; then
  AUTH=(-H "Authorization: Bearer ${API_KEY}")
fi

printf '== health ==\n'
curl -fsS "$API/health" | python -m json.tool
printf '== ready ==\n'
curl -fsS "$API/ready" | python -m json.tool
printf '== config/chunkers ==\n'
curl -fsS "${AUTH[@]}" "$API/v1/config/chunkers" | python -m json.tool

printf '== upload ==\n'
RESP=$(curl -fsS -X POST "$API/v1/documents" \
  "${AUTH[@]}" \
  -H "X-Tenant-ID: $TENANT" \
  -F "file=@examples/sample.md" \
  -F 'metadata={"suite":"smoke"}' \
  -F 'processing_options={"chunking":{"type":"hybrid","max_tokens":120},"deduplicate":false}')
echo "$RESP" | python -m json.tool
JOB_ID=$(python -c 'import json,sys; print(json.load(sys.stdin).get("job_id") or "")' <<<"$RESP")
if [[ -z "$JOB_ID" ]]; then
  echo 'No job_id returned' >&2
  exit 1
fi

printf '== wait for job ==\n'
DONE=0
for _ in $(seq 1 120); do
  JOB=$(curl -fsS "${AUTH[@]}" -H "X-Tenant-ID: $TENANT" "$API/v1/jobs/$JOB_ID")
  STATE=$(python -c 'import json,sys; print(json.load(sys.stdin)["state"])' <<<"$JOB")
  echo "state=$STATE"
  if [[ "$STATE" == "SUCCESS" ]]; then
    echo "$JOB" | python -m json.tool
    DONE=1
    break
  fi
  if [[ "$STATE" == "FAILURE" ]]; then
    echo "$JOB" | python -m json.tool
    exit 1
  fi
  sleep 2
done
if [[ "$DONE" != "1" ]]; then
  echo "Timed out waiting for ingestion job $JOB_ID" >&2
  exit 1
fi

printf '== rag search ==\n'
curl -fsS -X POST "$API/v1/rag/search" \
  "${AUTH[@]}" \
  -H "X-Tenant-ID: $TENANT" \
  -H 'Content-Type: application/json' \
  -d '{"query":"RAG document harness","mode":"hybrid","top_k":3,"candidate_k":10}' | python -m json.tool
