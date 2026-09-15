# Tests

Execute com:

```bash
PYTHONPATH=services/backend python -m unittest discover -s tests -v
```

A suíte cobre schemas dos três chunkers, retrieval, multi-corpus, ingestão direta de texto, Agent Profiles, os quatro providers LLM, mapeamento nativo do Ollama, extensões llama.cpp/vLLM e proteção de campos reservados do request ao LLM.
