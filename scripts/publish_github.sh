#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${1:-git@github.com:overcyber/docling-qdrant-rag-harness.git}"
BRANCH="${BRANCH:-main}"
MESSAGE="${COMMIT_MESSAGE:-Release docling-qdrant-rag-harness}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f .env ]]; then
  echo "ERROR: .env exists in project root. It is ignored by git, but verify that no secrets are staged." >&2
fi

if [[ ! -d .git ]]; then
  git init -b "$BRANCH"
fi

git branch -M "$BRANCH"

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi

git add .

# Safety checks before commit/push.
if git diff --cached --name-only | grep -Eq '(^|/)\.env$|(^|/)(id_rsa|id_ed25519)$|\.pem$|\.key$'; then
  echo "ERROR: potential secret-bearing file staged; aborting." >&2
  exit 2
fi

if ! git diff --cached --quiet; then
  git commit -m "$MESSAGE"
fi

git push -u origin "$BRANCH"
