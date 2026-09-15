# Exemplo de documento para o RAG Harness

Este documento existe apenas para o smoke test do projeto.

## Arquitetura

A plataforma utiliza Docling para parsing e chunking estrutural de documentos. O processamento pesado ocorre de forma assíncrona em workers Celery, usando Redis como broker e result backend.

## Busca

Os chunks são armazenados no banco vetorial Qdrant. Cada chunk possui um vetor denso semântico e um vetor esparso BM25. A consulta executa busca híbrida e combina as duas listas com Reciprocal Rank Fusion.

## Agente

O serviço RAG pode funcionar somente como retrieval API ou chamar um modelo de linguagem através de uma API compatível com OpenAI. As respostas retornam as fontes separadamente para permitir citações verificáveis no chatbot.
