# Consultas RAG e Visualização de Texto no Qdrant

Este guia explica detalhadamente:
1. **Onde e como o texto é armazenado no Qdrant** (no campo `payload`).
2. **Por que muitas vezes o texto parece não aparecer** e como visualizá-lo corretamente.
3. **Exemplos práticos de consultas RAG** (Híbrida, Densa, Esparsa, Montagem de Contexto e Chat com Memória).

---

## 1. Por que não vejo o texto diretamente no Qdrant?

No Qdrant, um ponto vetorial é composto por:
- **`id`**: Identificador único do chunk (UUID).
- **`vector`**: As representações matemáticas densas (embeddings do modelo, ex: 384 dimensões) e esparsas (BM25).
- **`payload`**: Objeto JSON com os metadados e o **texto original** do chunk.

### Principais motivos de dúvida:

1. **Consulta via API bruta do Qdrant sem `with_payload: true`**:
   Por padrão de eficiência, a API REST nativa do Qdrant (`/points/search` ou `/points/scroll`) **omite o payload** se você não solicitar explicitamente `{"with_payload": true}`. Sem isso, o Qdrant retorna apenas os IDs dos pontos e os scores vetoriais!
2. **Painel Web do Qdrant (Dashboard)**:
   No Qdrant Dashboard (`http://localhost:6333/dashboard`), os pontos são exibidos em lista resumida. É necessário clicar no ponto ou expandir a coluna de `payload` para ver os campos `text` e `contextualized_text`.
3. **Endpoints da API do Harness**:
   - `POST /v1/documents` retorna HTTP `202 Accepted` com `job_id` e `document_id`, mas não traz o texto (pois o processamento ocorre em background no Celery).
   - Para consultar o texto indexado de um documento, deve-se usar `GET /v1/documents/{document_id}` ou os endpoints de busca `POST /v1/rag/search`.

---

## 2. Estrutura do Payload no Qdrant

Cada chunk indexado pela nossa esteira salva os seguintes campos no Qdrant:

| Campo do Payload | Descrição |
|---|---|
| `text` | Texto extraído e fatiado pelo Docling para aquele chunk |
| `contextualized_text` | Texto enriquecido com os títulos/seções ancestrais do documento |
| `headings` | Lista hierárquica de seções e títulos onde o chunk está inserido |
| `pages` | Lista de páginas do PDF onde o chunk se encontra (ex: `[1]`, `[3, 4]`) |
| `page_provenance` | Nível de proveniência (`chunk` ou `document`) |
| `document_id` | UUID do documento original |
| `filename` | Nome do arquivo original (ex: `artigo.pdf`) |
| `sha256` | Hash SHA-256 do arquivo |
| `chunk_index` | Posição sequencial do chunk no documento (0, 1, 2...) |
| `chunker_type` | Estratégia utilizada (`hybrid`, `hierarchical`, `line_based`) |
| `tenant_id` | Identificador do tenant para isolamento de dados |
| `user_metadata` | Metadados arbitrários enviados no upload do arquivo |

---

## 3. Como Visualizar o Texto Diretamente no Qdrant

### Opção A: Pelo Qdrant Dashboard (Interface Web)

1. Acesse no navegador:
   ```text
   http://localhost:6333/dashboard
   ```
2. No menu lateral, clique em **Collections** e selecione `documents_v2`.
3. Clique na aba **Points**.
4. Clique sobre qualquer linha para expandir o JSON completo. O texto estará visível em:
   - `payload.text`
   - `payload.contextualized_text`

---

### Opção B: Pela API nativa do Qdrant com cURL

Para recuperar os pontos incluindo o texto completo, sempre inclua `"with_payload": true`:

```bash
curl -X POST http://localhost:6333/collections/documents_v2/points/scroll \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 3,
    "with_payload": true,
    "filter": {
      "must": [
        {"key": "tenant_id", "match": {"value": "mestrado-cybersec"}}
      ]
    }
  }'
```

---

## 4. Como Consultar o Texto pela API Unificada do Harness

A API pública do Harness (`:8000`) oferece endpoints de alto nível que já abstraem o Qdrant, formatando citações, metadados e scores.

### A. Obter todos os chunks e textos de um documento específico

Se você tem o `document_id` retornado no upload:

```bash
curl -X GET http://localhost:8000/v1/documents/SEU_DOCUMENT_ID \
  -H "X-Tenant-ID: mestrado-cybersec"
```

**Resposta:**
```json
{
  "document_id": "11b37cbf-4a06-4c1a-9018-7a255dfe4488",
  "filename": "An_Efficient_SQL_Injection_Detection_System_Using_Deep_Learning.pdf",
  "chunker_type": "hybrid",
  "chunks": [
    {
      "chunk_index": 0,
      "pages": [1],
      "headings": ["An Efficient SQL Injection Detection System Using Deep Learning"],
      "text": "Abstract—SQL Injection (SQLi) is one of the most critical threats..."
    }
  ],
  "returned_chunks": 49
}
```

---

### B. Busca Semântica RAG (`POST /v1/rag/search`)

A busca semântica converte a pergunta em vetor denso e tokens BM25, consulta o Qdrant e retorna os chunks mais relevantes com o texto integral e metadados de proveniência:

#### 1. Busca Híbrida (Recomendada - Dense + BM25 com RRF)
Combina proximidade vetorial semântica com correspondência exata de palavras-chave:

```bash
curl -X POST http://localhost:8000/v1/rag/search \
  -H "X-Tenant-ID: mestrado-cybersec" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Como redes neurais detectam ataques de injeção de SQL?",
    "mode": "hybrid",
    "top_k": 3,
    "candidate_k": 20
  }'
```

#### 2. Busca com Filtro de Metadados
Restringe a busca a determinados autores, categorias ou nomes de arquivos:

```bash
curl -X POST http://localhost:8000/v1/rag/search \
  -H "X-Tenant-ID: mestrado-cybersec" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "arquitetura do modelo e acurácia",
    "mode": "hybrid",
    "top_k": 5,
    "filters": {
      "filename": "An_Efficient_SQL_Injection_Detection_System_Using_Deep_Learning.pdf",
      "chunker_type": "hybrid"
    }
  }'
```

---

### C. Montagem de Contexto RAG para Agentes LLM (`POST /v1/rag/context`)

Este endpoint é ideal para quem está integrando o Harness com LangChain, LlamaIndex, agentes Autogen ou chamadas diretas a LLMs (Ollama, Claude, GPT). Ele já entrega o texto montado com identificadores de citação `[S1]`, `[S2]`:

```bash
curl -X POST http://localhost:8000/v1/rag/context \
  -H "X-Tenant-ID: mestrado-cybersec" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Quais são as métricas de acurácia obtidas pelo modelo MLP?",
    "mode": "hybrid",
    "top_k": 2
  }'
```

**Exemplo de Resposta:**
```json
{
  "query": "Quais são as métricas de acurácia obtidas pelo modelo MLP?",
  "tenant_id": "mestrado-cybersec",
  "context": "[S1] Documento: An_Efficient_SQL_Injection_Detection_System_Using_Deep_Learning.pdf (páginas [1])\nSeção: An Efficient SQL Injection Detection System Using Deep Learning\nCom o auxílio do modelo MLP alcançamos uma acurácia de validação cruzada de 98% com precisão de 98% e revocação de 97%.\n\n[S2] Documento: ...",
  "sources": [
    {
      "citation": "S1",
      "score": 0.75,
      "document_id": "11b37cbf-4a06-4c1a-9018-7a255dfe4488",
      "filename": "An_Efficient_SQL_Injection_Detection_System_Using_Deep_Learning.pdf",
      "pages": [1],
      "text": "..."
    }
  ]
}
```

---

### D. Chat RAG com Memória de Conversa (`POST /v1/rag/chat`)

Permite conversas com histórico retido no Redis:

```bash
curl -X POST http://localhost:8000/v1/rag/chat \
  -H "X-Tenant-ID: mestrado-cybersec" \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "sessao-pesquisa-01",
    "question": "Qual é a precisão do modelo apresentado no artigo?",
    "retrieval": {
      "mode": "hybrid",
      "top_k": 3
    }
  }'
```

---

## 5. Exemplo Completo em Python

Você pode rodar este script em qualquer ambiente que tenha acesso à porta `8000`:

```python
import requests
import json

API_URL = "http://localhost:8000"
TENANT = "mestrado-cybersec"

def buscar_evidencias(pergunta: str):
    response = requests.post(
        f"{API_URL}/v1/rag/search",
        headers={"X-Tenant-ID": TENANT},
        json={
            "query": pergunta,
            "mode": "hybrid",
            "top_k": 3
        }
    )
    dados = response.json()
    
    print(f"\n=== Pergunta: {pergunta} ===")
    for item in dados.get("results", []):
        print(f"\n[{item['citation']}] Score: {item['score']:.4f} | Arquivo: {item['filename']} (Pág: {item['pages']})")
        print(f"Seção: {' > '.join(item['headings'])}")
        print(f"Texto extraído:\n{item['text']}\n" + "-"*50)

if __name__ == "__main__":
    buscar_evidencias("Quais algoritmos de deep learning foram avaliados para detecção de anomalias?")
```
