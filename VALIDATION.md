# Validation status

Version: `2.1.0`

## Build-time validation

A validação automatizada cobre:

- compilação sintática de todos os serviços Python;
- schemas dos três chunkers e três modos de retrieval;
- schemas dos quatro providers LLM;
- ingestão direta de texto, multi-corpus e Agent Profile;
- payloads nativos do Ollama e extensões llama.cpp/vLLM;
- YAML estrutural do Docker Compose;
- presença dos serviços core e profiles opcionais;
- MkDocs/navigation;
- notebook Colab JSON + sintaxe das code cells;
- OpenAPI da FastAPI quando as dependências runtime estão instaladas;
- criação do schema do control plane em SQLite para teste sem dependência externa;
- shell syntax dos scripts;
- ausência de arquivos de secrets conhecidos no pacote.

Execute:

```bash
./scripts/validate.sh
```

## Runtime integration

Após iniciar os containers:

```bash
./scripts/smoke_test.sh
```

O smoke test verifica readiness, ingestão direta de texto assíncrona e busca híbrida limitada ao corpus de teste.

## Limitação do ambiente de construção

Este ambiente de construção não expõe daemon Docker/Podman; `docker compose up` não foi executado aqui. A validação estática e unitária foi concluída, mas o smoke test deve ser executado num host com Docker.
