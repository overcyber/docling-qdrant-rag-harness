# Docling Qdrant Advanced RAG Agent Harness

Harness de microserviços para ingestão documental em volume e RAG avançado com **Docling**, **Qdrant**, **Redis/Celery**, **PostgreSQL** e uma API pública **FastAPI**. A versão 2.1 incorpora as partes úteis do ingestor/chatbot legado sem regredir o pipeline atual.

## Capacidades

- ingestão assíncrona de PDF, DOCX, TXT e Markdown;
- ingestão direta de texto via JSON (`POST /v1/documents/text`);
- três chunkers Docling: `hybrid`, `hierarchical` e `line_based`;
- embeddings dense + sparse e retrieval `hybrid` com RRF;
- reranking opcional;
- `corpus_id` lógico e consulta multi-corpus sem criar uma collection Qdrant por chatbot;
- API RAG de busca, contexto, chat e **streaming SSE**;
- providers LLM explícitos: **OpenAI-compatible, Ollama, llama.cpp server e vLLM**;
- descoberta de modelos nos runtimes suportados;
- parâmetros avançados de geração (`temperature`, `top_p`, `top_k`, `min_p`, penalties, Mirostat e extensões controladas);
- PostgreSQL como control plane para **corpora, prompt templates e agent profiles**;
- memória conversacional curta em Redis, configurável por agente;
- NATS opcional como event bus; Celery/Redis continua sendo a fila de trabalho;
- multi-tenant por `X-Tenant-ID`;
- deduplicação por conteúdo + corpus + perfil de processamento + metadata, com reserva atômica no Redis;
- Swagger, ReDoc, MkDocs, testes, GitHub Actions e notebook Colab.

## Arquitetura

```text
Client / UI / Agent
        |
        v
+------------------------------------------+
| FastAPI :8000                            |
| documents | RAG | streaming | agents    |
+----+----------------+--------------------+
     |                |
     |                +----> PostgreSQL
     |                      corpora / prompts / agents / audit
     |
     +----> Redis/Celery ----> Worker
     |                           |----> Docling parser
     |                           |----> Embedder
     |                           +----> Qdrant
     |
     +----> Embedder ----> Qdrant ----> RRF/rerank
     |
     +----> Redis conversation memory
     |
     +----> LLM provider
     |       |-- OpenAI-compatible
     |       |-- Ollama native /api/chat
     |       |-- llama.cpp server /v1/chat/completions
     |       +-- vLLM /v1/chat/completions
     |
     +----> NATS (optional event bus)
```

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
```

Verifique:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Swagger: `http://localhost:8000/docs`  
ReDoc: `http://localhost:8000/redoc`

## Ingestão de arquivo

```bash
curl -X POST http://localhost:8000/v1/documents \
  -H 'X-Tenant-ID: lab' \
  -F 'file=@report.pdf' \
  -F 'corpus_id=tese' \
  -F 'metadata={"project":"alpha"}' \
  -F 'processing_options={"chunking":{"type":"hybrid","max_tokens":120}}'
```

## Ingestão direta de texto

```bash
curl -X POST http://localhost:8000/v1/documents/text \
  -H 'X-Tenant-ID: lab' \
  -H 'Content-Type: application/json' \
  -d '{
    "title":"Nota experimental",
    "text":"Conteúdo que deve entrar no RAG sem criar um arquivo manualmente.",
    "corpus_id":"experimentos",
    "metadata":{"source":"api"},
    "processing_options":{"chunking":{"type":"hybrid"}}
  }'
```

## Busca multi-corpus

```bash
curl -X POST http://localhost:8000/v1/rag/search \
  -H 'X-Tenant-ID: lab' \
  -H 'Content-Type: application/json' \
  -d '{
    "query":"Quais evidências sustentam a hipótese?",
    "mode":"hybrid",
    "corpora":["tese","papers","experimentos"],
    "top_k":8,
    "candidate_k":40,
    "rerank":true
  }'
```

## Providers LLM

Selecione o provider globalmente com `LLM_PROVIDER` ou por requisição/Agent Profile.

| Provider | API usada pelo harness | Profile Docker |
|---|---|---|
| `openai_compatible` | `/v1/chat/completions` ou base configurada | externo |
| `ollama` | API nativa `/api/chat`; `/api/tags` para descoberta | `ollama` |
| `llama_cpp` | `/v1/chat/completions`; `/v1/models` | `llama-cpp` |
| `vllm` | `/v1/chat/completions`; `/v1/models` | `vllm` |

Exemplo Ollama:

```bash
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:8b

docker compose --profile ollama up -d ollama
docker compose exec ollama ollama pull qwen3:8b
```

Exemplo llama.cpp server:

```bash
mkdir -p models/llama.cpp
# copie seu GGUF para models/llama.cpp/model.gguf

LLM_PROVIDER=llama_cpp
LLAMA_CPP_MODEL=auto
LLAMA_CPP_MODEL_PATH=/models/model.gguf

docker compose --profile llama-cpp up -d llama-cpp
```

Veja [docs/llm-providers.md](docs/llm-providers.md).

## Streaming SSE

```bash
curl -N -X POST http://localhost:8000/v1/rag/chat/stream \
  -H 'X-Tenant-ID: lab' \
  -H 'Content-Type: application/json' \
  -d '{
    "question":"Resuma os achados e cite as fontes.",
    "corpora":["tese"],
    "provider":"ollama",
    "model":"qwen3:8b"
  }'
```

Eventos: `retrieval`, `source`, `model`, `token`, `completion` e `error`.

## Agent Profiles e prompts

O control plane PostgreSQL mantém configuração durável, sem armazenar chaves de API nos perfis:

```text
/v1/corpora
/v1/prompt-templates
/v1/agents
/v1/agents/{agent_id}/chat
/v1/agents/{agent_id}/chat/stream
```

Um perfil pode fixar corpora, provider/model, retrieval, geração, prompt e política de memória. Veja [docs/control-plane.md](docs/control-plane.md).

## NATS opcional

Celery/Redis continua responsável pelos jobs. NATS é apenas event bus para eventos como `document.started`, `document.indexed`, `document.failed` e `query.completed`.

```bash
NATS_ENABLED=true
docker compose --profile events up -d nats
```

## Documentação

- [Quick start](docs/quickstart.md)
- [Architecture](docs/architecture.md)
- [API guide](docs/api.md)
- [Chunking](docs/chunking.md)
- [LLM providers](docs/llm-providers.md)
- [Control plane / Agent Profiles](docs/control-plane.md)
- [Legacy port matrix](docs/legacy-port.md)
- [Configuration](docs/configuration.md)
- [Agent integration](docs/agent-integration.md)
- [Google Colab](docs/colab.md)
- [Operations](docs/operations.md)
- [Security](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Validation status](VALIDATION.md)

Standalone MkDocs:

```bash
docker compose --profile documentation up -d docs
```

## Validação

```bash
./scripts/validate.sh
```

Com os containers ativos:

```bash
./scripts/smoke_test.sh
```

## GitHub

Repositório: `overcyber/docling-qdrant-rag-harness`.
