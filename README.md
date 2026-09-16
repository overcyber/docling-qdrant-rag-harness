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

## Suporte a GPU NVIDIA via Docker

Para acelerar os modelos neurais do **Docling** (Layout detection, TableFormer, OCR) e os modelos de embeddings utilizando a GPU NVIDIA do host:

### 1. Configurar o repositório do NVIDIA Container Toolkit

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
```

### 2. Instalar o Toolkit

Atualize a lista de pacotes locais e instale o pacote `nvidia-container-toolkit`:

```bash
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
```

### 3. Configurar o Container Runtime

Configure o runtime correspondente ao seu ambiente para usar a camada de driver NVIDIA:

#### Para Docker 🐋
Atualiza o arquivo `/etc/docker/daemon.json` e reinicia o serviço Docker:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

#### Para Containerd 📦
Atualiza o arquivo `/etc/containerd/config.toml` e reinicia o containerd:

```bash
sudo nvidia-ctk runtime configure --runtime=containerd
sudo systemctl restart containerd
```

### 4. Verificar a Instalação

Verifique se os containers conseguem se comunicar com a sua GPU executando um container de teste CUDA leve:

```bash
sudo docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

### 5. Iniciar o Harness com suporte a GPU

Para inicializar a stack com aceleração por hardware NVIDIA GPU no Docling Parser (detecção de layout, OCR e extração estrutural aceleradas via CUDA):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Para inicializar o ambiente apenas em modo CPU:

```bash
docker compose up -d
```

Verifique se o serviço de parser Docling detectou e inicializou o dispositivo CUDA através do readiness probe:

```bash
curl http://localhost:8000/ready
# Retorna: {"status":"ready","checks":{"parser_cuda":true,"parser_device":"NVIDIA GeForce RTX ...",...}}
```

E consulte o `/health` direto do parser Docling:

```bash
curl http://localhost:8001/health
# Retorna: {"status":"ok","cuda_available":true,"cuda_device":"NVIDIA GeForce RTX ...","cuda_device_count":1}
```

## Ingestão de arquivo

```bash
curl -X POST http://localhost:8000/v1/documents \
  -H 'X-Tenant-ID: lab' \
  -F 'file=@report.pdf' \
  -F 'corpus_id=tese' \
  -F 'metadata={"project":"alpha"}' \
  -F 'processing_options={"chunking":{"type":"hybrid","max_tokens":120}}'
```

### Verificação prévia de duplicata (`GET /v1/documents/check`)

Antes de enviar arquivos volumosos pela rede, é possível consultar instantaneamente se o documento já está indexado por SHA-256 ou fingerprint:

```bash
curl -X GET "http://localhost:8000/v1/documents/check?sha256=<HASH_64_CHARS>&corpus_id=tese" \
  -H 'X-Tenant-ID: lab'
# Retorna: {"exists":true,"document_id":"...","filename":"...","corpus_id":"tese","chunker_type":"hybrid"}
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

## Ingestão em lote de pastas (`scripts/ingest_folder.py`)

Para processar diretórios inteiros contendo dezenas ou centenas de documentos (`.pdf`, `.docx`, `.txt`, `.md`), utilize o script CLI [`scripts/ingest_folder.py`](scripts/ingest_folder.py).

### Principais recursos:
- **Verificação Prévia Instantânea (Pre-check)**: Calcula o hash SHA-256 localmente em milissegundos e consulta `/v1/documents/check`. Arquivos já ingeridos são ignorados imediatamente sem tráfego de rede desnecessário, sem escrita temporária em disco e sem filas no Celery.
- **Detecção de GPU em Tempo Real**: Consulta a API e exibe no cabeçalho se a aceleração CUDA está ativa no Docling Parser.
- **Suporte a Múltiplos Corpora**: Parâmetro `--corpus` / `--corpus-id` para direcionar a ingestão para um namespace lógico específico (ex: `seguranca`, `tese`).
- **Controle de Concorrência**: Envia arquivos e acompanha as tarefas Celery em paralelo via `--concurrency N`.
- **Estratégias de Chunking**: Permite selecionar `--chunker hybrid`, `hierarchical` ou `line_based` e definir `--max-tokens`.
- **OCR sob Demanda**: Flag `--ocr` opcional para documentos digitalizados ou imagens.
- **Forçar Reingestão**: Flag `--force` para reindexar documentos mesmo que já existam.

### Exemplos práticos:

```bash
# 1. Ingestão padrão híbrida com aceleração GPU e pre-check de duplicatas
python3 scripts/ingest_folder.py \
  --dir /opt/pdf-ingestao \
  --tenant mestrado-cybersec \
  --corpus seguranca \
  --chunker hybrid \
  --max-tokens 120 \
  --concurrency 2

# 2. Ingestão com OCR ativado e chunker hierárquico
python3 scripts/ingest_folder.py \
  --dir /opt/pdf-ingestao \
  --tenant mestrado-cybersec \
  --chunker hierarchical \
  --ocr \
  --concurrency 2

# 3. Teste rápido com apenas 1 documento (para validar o pipeline e GPU)
python3 scripts/ingest_folder.py \
  --dir /opt/pdf-ingestao \
  --tenant mestrado-cybersec \
  --limit 1

# 4. Teste em lote com concorrência direta
python3 scripts/ingest_folder.py \
  --dir /opt/pdf-ingestao \
  --tenant mestrado-cybersec \
  --concurrency 2
```

**Exemplo de saída no terminal:**
```text
===========================================================================
📁 Diretório:    /opt/pdf-ingestao (76 arquivos)
🏢 Tenant:       mestrado-cybersec | Corpus: default
⚙️  Chunker:      hybrid (max_tokens: 120) | OCR: False
🔄 Concorrência: 2 | Forçar Reingestão: False
🚀 Aceleração:   CUDA ATIVO (NVIDIA GeForce RTX 5060 Laptop GPU)
===========================================================================
[1/76] ⏭️  JÁ INGERIDO (IGNORADO): 24-1-MDM-apresentacoes.pdf [pre-check instantâneo] (ID existente: 99580fbd...)
[2/76] ⏭️  JÁ INGERIDO (IGNORADO): A Survey on Data Selection... [pre-check instantâneo] (ID existente: 8b9d66b7...)
[3/76] ✅ NOVO INGERIDO: Detection of SQL injection.pdf -> 149 chunks [GPU: NVIDIA GeForce RTX 5060 Laptop GPU] em 6.4s (ID: 4f82b6fc...)
...
===========================================================================
🏁 Concluído em 45.2s
📊 Resumo: Novos Ingeridos: 12 | Já Ingeridos (Ignorados): 64 | Falhas: 0 | Novos Chunks: 1840
===========================================================================
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

## Montagem de contexto RAG (`POST /v1/rag/context`)

Para agentes externos (LangChain, LlamaIndex, agentes Autogen ou chamadas diretas a LLMs), este endpoint realiza a recuperação híbrida no Qdrant e formata o bloco textual pronto para prompt com marcadores de citação `[S1]`, `[S2]`:

```bash
curl -X POST http://localhost:8000/v1/rag/context \
  -H 'X-Tenant-ID: lab' \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "Quais métricas de acurácia foram obtidas pelo modelo?",
    "corpora": ["tese"],
    "mode": "hybrid",
    "top_k": 3
  }'
```

## Exemplo de uso em Python (Consumo RAG)

Script limpo e direto para buscar evidências e consumir o RAG a partir de qualquer aplicação Python:

```python
import requests

API_URL = "http://localhost:8000"
TENANT = "mestrado-cybersec"

def consultar_rag(pergunta: str, corpus: str = "massivos"):
    response = requests.post(
        f"{API_URL}/v1/rag/search",
        headers={"X-Tenant-ID": TENANT},
        json={
            "query": pergunta,
            "corpora": [corpus],
            "mode": "hybrid",
            "top_k": 3
        }
    )
    dados = response.json()
    print(f"\n=== Pergunta: {pergunta} ===")
    for item in dados.get("results", []):
        print(f"\n[{item['citation']}] Score: {item['score']:.4f} | Arquivo: {item['filename']} (Pág: {item['pages']})")
        print(f"Seção: {' > '.join(item.get('headings', []))}")
        print(f"Texto extraído:\n{item['text'][:280]}...\n" + "-"*50)

if __name__ == "__main__":
    consultar_rag("Como redes neurais detectam ataques de injeção de SQL?")
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
- [RAG Queries & Qdrant](docs/rag-querying.md) — Visualização de texto no Qdrant, payload e exemplos de busca
- [Chunking](docs/chunking.md)
- [LLM providers](docs/llm-providers.md)
- [Control plane / Agent Profiles](docs/control-plane.md)
- [Legacy port matrix](docs/legacy-port.md)
- [Configuration](docs/configuration.md)
- [Agent integration](docs/agent-integration.md)
- [Google Colab](docs/colab.md)
- [Operations & GPU](docs/operations.md) — Escalonamento, tolerância a falhas e ativação de GPU
- [Security](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Validation status](VALIDATION.md)

Standalone MkDocs:

```bash
docker compose --profile documentation up -d docs
```

## Scripts e Validação

O projeto conta com scripts utilitários prontos para automação, ingestão em lote e verificação:

| Script | Função | Exemplo de Execução |
|---|---|---|
| [`scripts/ingest_folder.py`](scripts/ingest_folder.py) | Ingestão em lote de pastas com **detecção automática de duplicatas por SHA-256** | `python3 scripts/ingest_folder.py --dir /caminho --tenant lab --chunker hybrid` |
| [`scripts/smoke_test.sh`](scripts/smoke_test.sh) | Smoke test ponta a ponta na stack ativa (upload, parser, embedder e busca híbrida) | `./scripts/smoke_test.sh` |
| [`scripts/validate.sh`](scripts/validate.sh) | Validação estática, checagem de schemas Pydantic, OpenAPI, MkDocs e **22 testes E2E** | `./scripts/validate.sh` |

Para rodar a suíte completa de validação:

```bash
./scripts/validate.sh
```

Com os containers ativos, para rodar o teste rápido de fumaça:

```bash
./scripts/smoke_test.sh
```

## GitHub

Repositório: `overcyber/docling-qdrant-rag-harness`.
