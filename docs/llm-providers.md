# LLM providers

O harness possui uma interface única de chat, mas mantém adaptadores explícitos para preservar as capacidades de cada runtime.

## Providers suportados

| Nome | Transporte | Streaming | Descoberta | Extensões |
|---|---|---:|---|---|
| `openai_compatible` | Chat Completions | sim | `/models` | `extra_body` seguro |
| `ollama` | API nativa `/api/chat` | sim, NDJSON | `/api/tags` | `top_k`, `repeat_penalty`, Mirostat, `think`, `keep_alive`, etc. |
| `llama_cpp` | `/v1/chat/completions` | sim, SSE | `/v1/models` | `top_k`, `min_p`, repetition penalty, Mirostat e campos extras aceitos pelo servidor |
| `vllm` | `/v1/chat/completions` | sim, SSE | `/v1/models` | `top_k`, `min_p`, `repetition_penalty` e parâmetros adicionais |

`extra_body` nunca pode substituir `model`, `messages` ou `stream`; esses campos são controlados pelo servidor para proteger o grounding e o protocolo de streaming.

## Seleção

Global:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:8b
```

Por request:

```json
{
  "question": "Explique a evidência.",
  "provider": "llama_cpp",
  "model": "auto",
  "generation": {
    "temperature": 0.1,
    "top_p": 0.9,
    "top_k": 40,
    "min_p": 0.05,
    "max_tokens": 2048,
    "repetition_penalty": 1.05
  }
}
```

Quando `model` está vazio ou vale `auto`, o adaptador tenta descobrir o primeiro modelo anunciado pelo runtime.

## OpenAI-compatible genérico

```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://example.internal/v1
LLM_API_KEY=...
LLM_MODEL=my-model
```

## Ollama

O adaptador usa a API nativa, não apenas a camada OpenAI-compatible.

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen3:8b
```

```bash
docker compose --profile ollama up -d ollama
docker compose exec ollama ollama pull qwen3:8b
```

Mapeamentos nativos relevantes:

| Harness | Ollama |
|---|---|
| `max_tokens` | `options.num_predict` |
| `repetition_penalty` | `options.repeat_penalty` |
| `top_k` | `options.top_k` |
| `mirostat*` | `options.mirostat*` |

## llama.cpp server

```bash
mkdir -p models/llama.cpp
cp /caminho/model.gguf models/llama.cpp/model.gguf
```

```dotenv
LLM_PROVIDER=llama_cpp
LLAMA_CPP_BASE_URL=http://llama-cpp:8080/v1
LLAMA_CPP_MODEL=auto
LLAMA_CPP_MODEL_PATH=/models/model.gguf
LLAMA_CPP_CONTEXT_SIZE=8192
```

```bash
docker compose --profile llama-cpp up -d llama-cpp
```

O serviço Docker usa `ghcr.io/ggml-org/llama.cpp:server` por padrão.

## vLLM

```dotenv
LLM_PROVIDER=vllm
VLLM_MODEL=Qwen/Qwen3-8B
VLLM_BASE_URL=http://vllm:8000/v1
```

```bash
docker compose --profile vllm up -d vllm
```

## Descoberta via API

```http
GET /v1/llm/providers
GET /v1/llm/providers/{provider}/models
```

Nenhuma chave é devolvida pela API de configuração.
