# Changelog

## 2.1.0 — 2026-09-15

- Porta ingestão direta de texto do projeto legado para o mesmo pipeline assíncrono Docling → chunking → embeddings → Qdrant.
- Introduz `corpus_id` lógico, filtro multi-corpus e inclui corpus no fingerprint de deduplicação.
- Adiciona streaming SSE em `/v1/rag/chat/stream` e streaming por Agent Profile.
- Adiciona quatro providers nomeados: `openai_compatible`, `ollama`, `llama_cpp` e `vllm`.
- Usa API nativa do Ollama (`/api/chat`) e preserva parâmetros específicos; llama.cpp e vLLM usam Chat Completions com extensões próprias.
- Adiciona descoberta de modelos e parâmetros avançados de geração, com proteção contra override de `model`, `messages` e `stream`.
- Adiciona PostgreSQL como control plane para corpora, prompt templates, Agent Profiles e audit.
- Adiciona profiles Docker opcionais para Ollama, llama.cpp, vLLM e NATS.
- Adiciona NATS opcional como event bus; Celery/Redis permanece fila autoritativa.
- Mantém Docling, os três chunkers, Qdrant hybrid RRF, provenance, embedding-space guard e isolamento lógico por tenant.
- Não porta PyPDF/PyMuPDF, CharacterTextSplitter, LangChain RetrievalQA, Docker socket manager, locks globais nem credenciais hard-coded do legado.

## 2.0.0 — 2026-09-15

- Unifica ingestão e RAG em uma única API FastAPI pública na porta `8000`.
- Adiciona configuração global e override por documento para os três chunkers: `hybrid`, `hierarchical` e `line_based`.
- Adiciona opções de PDF/Docling por ingestão: OCR, estrutura de tabelas, cell matching, limite de páginas e page range.
- Adiciona retrieval `hybrid`, `dense` e `sparse`, filtros de metadata e filtros diretos por `chunker_type`, RRF, threshold, reranker opcional e guarda de identidade do espaço de embeddings.
- Adiciona endpoints de introspecção segura de configuração e descrição dos chunkers.
- Adiciona documentação MkDocs Material, Swagger e ReDoc.
- Adiciona memória de conversa em Redis e adaptador de LLM OpenAI-compatible.
- Adiciona isolamento por tenant, deduplicação por conteúdo+perfil de processamento+metadados, reserva Redis contra duplicatas concorrentes e ownership de jobs.
- Atualiza exemplos, smoke test, validação estática e notebook Google Colab.
- Adiciona GitHub Actions para validação estática, schemas, notebook e `docker compose config`.

- Added `scripts/publish_github.sh` for deterministic publication to the private GitHub repository with basic secret-file staging checks.
