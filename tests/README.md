# Tests

Static validation:

```bash
./scripts/validate.sh
```

Schema unit tests (requires backend Python dependencies):

```bash
PYTHONPATH=services/backend python -m unittest tests/test_schemas.py
```

Full integration smoke test after Docker Compose is running:

```bash
./scripts/smoke_test.sh
```
