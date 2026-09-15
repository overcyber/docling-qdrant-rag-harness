#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python -m compileall -q "$ROOT/services"

python - "$ROOT" <<'PY'
import ast, json, os, pathlib, sys, yaml
root=pathlib.Path(sys.argv[1])
compose = yaml.safe_load((root/'docker-compose.yml').read_text())
mkdocs = yaml.safe_load((root/'mkdocs.yml').read_text())
notebook = json.loads((root/'colab/RAG_Harness_Colab.ipynb').read_text())
services = compose['services']
for required in ('api','worker','redis','qdrant','postgres','parser-docling','embedder'):
    assert required in services, f'missing core service: {required}'
for optional, profile in (('docs','documentation'), ('flower','monitoring'), ('nats','events'), ('ollama','ollama'), ('ollama-pull','ollama-pull'), ('llama-cpp','llama-cpp'), ('vllm','vllm')):
    assert optional in services, f'missing optional service: {optional}'
    assert profile in services[optional].get('profiles', []), f'{optional} missing profile {profile}'
api_deps=services['api'].get('depends_on', {})
for dependency in ('redis','qdrant','postgres','parser-docling','embedder'):
    assert dependency in api_deps, f'api missing dependency {dependency}'
def targets(node):
    if isinstance(node, str): yield node
    elif isinstance(node, list):
        for x in node: yield from targets(x)
    elif isinstance(node, dict):
        for x in node.values(): yield from targets(x)
for target in targets(mkdocs.get('nav', [])):
    assert (root/'docs'/target).exists(), f'MkDocs nav target not found: {target}'
for idx, cell in enumerate(notebook.get('cells', [])):
    if cell.get('cell_type') != 'code': continue
    source = ''.join(cell.get('source', []))
    source = '\n'.join(line for line in source.splitlines() if not line.lstrip().startswith(('%', '!')))
    if source.strip(): ast.parse(source, filename=f'colab-cell-{idx}')
for forbidden in ('8003', 'CHUNK_MAX_TOKENS=420'):
    for path in list((root/'docs').glob('*.md')) + [root/'README.md', root/'docker-compose.yml']:
        assert forbidden not in path.read_text(), f'stale token {forbidden!r} in {path}'
for forbidden_path in (root/'id_rsa', root/'id_ed25519'):
    assert not forbidden_path.exists(), f'secret-like file must not be packaged: {forbidden_path.name}'
if os.getenv('CI'):
    assert not (root/'.env').exists(), 'secret-like file must not be packaged: .env'
assert not list(root.rglob('*.pem')), 'PEM files must not be packaged'
assert not list(root.rglob('*.key')), 'KEY files must not be packaged'
print('static validation: OK')
PY

PYTHONPATH="$ROOT/services/backend" python - <<'PY'
from app.schemas import ChatRequest, ProcessingOptions, TextIngestRequest
for payload in [{'chunking': {'type':'hybrid','max_tokens':512}}, {'chunking': {'type':'hierarchical'}}, {'chunking': {'type':'line_based','max_tokens':256}}]: ProcessingOptions.model_validate(payload)
TextIngestRequest(text='text input', corpus_id='demo')
for provider in ('openai_compatible','ollama','llama_cpp','vllm'): ChatRequest(question='q', provider=provider)
print('schema validation: OK')
PY

if python -c 'import redis, celery, qdrant_client' >/dev/null 2>&1; then
  PYTHONPATH="$ROOT/services/backend" CONTROL_PLANE_ENABLED=false python - <<'PY'
from app.api import app
paths=app.openapi().get('paths', {})
for expected in ('/v1/documents/text', '/v1/rag/chat/stream', '/v1/corpora', '/v1/prompt-templates', '/v1/agents', '/v1/llm/providers'):
    assert expected in paths, f'missing OpenAPI path: {expected}'
print('openapi validation: OK')
PY
else
  echo 'openapi validation: SKIPPED (runtime backend dependencies not installed in this host)'
fi

if python -c 'import sqlalchemy' >/dev/null 2>&1; then
  PYTHONPATH="$ROOT/services/backend" CONTROL_PLANE_ENABLED=true CONTROL_PLANE_AUTO_CREATE=true DATABASE_URL='sqlite+pysqlite:///:memory:' python - <<'PY'
from app.control_plane import init_control_plane, engine
init_control_plane()
tables=set(__import__('sqlalchemy').inspect(engine()).get_table_names())
for expected in ('rag_corpora','rag_prompt_templates','rag_agent_profiles','rag_audit_events'):
    assert expected in tables, f'missing control-plane table: {expected}'
print('control-plane schema validation: OK')
PY
else
  echo 'control-plane schema validation: SKIPPED (sqlalchemy not installed in this host)'
fi

PYTHONPATH="$ROOT/services/backend" python -m unittest discover -s "$ROOT/tests" -v
bash -n "$ROOT/scripts/smoke_test.sh"
bash -n "$ROOT/scripts/publish_github.sh"
echo 'validation completed'
