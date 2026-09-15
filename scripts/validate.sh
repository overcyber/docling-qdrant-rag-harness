#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python -m compileall -q "$ROOT/services"
python - "$ROOT" <<'PY'
import ast, json, pathlib, sys, yaml
root=pathlib.Path(sys.argv[1])
compose = yaml.safe_load((root/'docker-compose.yml').read_text())
mkdocs = yaml.safe_load((root/'mkdocs.yml').read_text())
notebook = json.loads((root/'colab/RAG_Harness_Colab.ipynb').read_text())
assert 'api' in compose['services'] and 'redis' in compose['services'] and 'qdrant' in compose['services']
assert 'parser-docling' in compose['services']['api'].get('depends_on', {})
assert 'docs' in compose['services'] and 'documentation' in compose['services']['docs'].get('profiles', [])
for entry in mkdocs.get('nav', []):
    target = next(iter(entry.values()))
    assert (root/'docs'/target).exists(), f'MkDocs nav target not found: {target}'
for idx, cell in enumerate(notebook.get('cells', [])):
    if cell.get('cell_type') != 'code':
        continue
    source = ''.join(cell.get('source', []))
    source = '\n'.join(
        line for line in source.splitlines()
        if not line.lstrip().startswith(('%', '!'))
    )
    if source.strip():
        ast.parse(source, filename=f'colab-cell-{idx}')
for forbidden in ('8003', 'CHUNK_MAX_TOKENS=420'):
    for path in list((root/'docs').glob('*.md')) + [root/'README.md', root/'docker-compose.yml']:
        assert forbidden not in path.read_text(), f'stale token {forbidden!r} in {path}'
print('static validation: OK')
PY

PYTHONPATH="$ROOT/services/backend" python - <<'PY'
from app.schemas import ProcessingOptions
for payload in [
    {'chunking': {'type':'hybrid','max_tokens':512}},
    {'chunking': {'type':'hierarchical'}},
    {'chunking': {'type':'line_based','max_tokens':256}},
]:
    ProcessingOptions.model_validate(payload)
print('schema validation: OK')
PY


PYTHONPATH="$ROOT/services/backend" python -m unittest discover -s "$ROOT/tests" -v

echo 'validation completed'
