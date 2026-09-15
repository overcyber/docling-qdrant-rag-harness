# Changelog

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
