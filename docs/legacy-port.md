# Port matrix do projeto legado

A versão 2.1 reutiliza conceitos do ingestor/chatbot antigo, mas preserva o núcleo moderno Docling/Qdrant.

| Recurso legado | Estado 2.1 | Estratégia |
|---|---|---|
| Ingestão direta de texto | **portado** | `/v1/documents/text`, mesmo pipeline do arquivo |
| Streaming SSE | **portado e reescrito** | `/v1/rag/chat/stream` e streaming por Agent Profile |
| vLLM local | **portado** | profile Docker opcional `vllm` |
| Ollama | **upgrade novo** | adaptador nativo + profile Docker |
| llama.cpp server | **upgrade novo** | adaptador explícito + profile Docker oficial |
| Seleção de collection/corpus | **portado como conceito** | `corpus_id` lógico e busca multi-corpus |
| Prompt templates | **portado** | PostgreSQL + CRUD |
| Chatbot configuration | **portado e evoluído** | Agent Profiles duráveis |
| Parâmetros avançados do LLM | **portado e ampliado** | parâmetros comuns + extensões por provider |
| PostgreSQL | **portado com novo papel** | control plane e audit |
| NATS | **portado opcionalmente** | event bus; não substitui Celery |
| Retorno de fontes | **mantido do harness novo** | provenance estruturada `[S1]...` |
| PyPDF/PyMuPDF | **não portado** | Docling permanece parser canônico |
| CharacterTextSplitter | **não portado** | 3 chunkers Docling permanecem canônicos |
| LangChain RetrievalQA | **não portado** | pipeline explícito facilita métricas e controle |
| Manager com Docker socket | **não portado** | profiles/configuração são dados, não containers por chatbot |
| Locks globais na API | **não portado** | concorrência delegada aos runtimes/filas |
| Credenciais hard-coded do legado | **não portado** | secrets somente por ambiente/secret manager |

A regra foi portar **capacidade** sem portar dívida técnica.
