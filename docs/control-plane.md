# Control plane: corpora, prompts e agents

A versão 2.1 separa data plane e control plane.

```text
Qdrant      = chunks + vetores + metadata de retrieval
Redis       = Celery, locks/dedupe, cache e memória curta
PostgreSQL  = corpora, prompt templates, agent profiles e audit
NATS        = eventos opcionais
```

## Corpora

`corpus_id` é um namespace lógico dentro da collection Qdrant. Ele evita a estratégia antiga de criar uma collection física para cada chatbot.

Endpoints:

```text
POST   /v1/corpora
GET    /v1/corpora
GET    /v1/corpora/{corpus_id}
PUT    /v1/corpora/{corpus_id}
DELETE /v1/corpora/{corpus_id}
```

Excluir a entrada do registry **não remove vetores**. A exclusão documental continua explícita pelo endpoint de documentos.

A ingestão aceita `corpus_id`, e a busca/chat aceita `corpora: []`. Se a lista estiver vazia, busca-se em todos os corpora do tenant.

## Prompt templates

Endpoints CRUD:

```text
/v1/prompt-templates
```

Um template contém `system_prompt` e um `model_hint` opcional. O template não contém segredos.

## Agent Profiles

Um Agent Profile é uma configuração durável de provider/modelo, prompt template, corpora, retrieval, geração, política de memória, welcome message e visibilidade de fontes.

Chat:

```text
POST /v1/agents/{agent_id}/chat
POST /v1/agents/{agent_id}/chat/stream
```

Parâmetros fornecidos na chamada podem sobrescrever o perfil. Chaves de API continuam exclusivamente em variáveis de ambiente/secret manager.

## PostgreSQL

O schema é criado automaticamente por padrão (`CONTROL_PLANE_AUTO_CREATE=true`). O startup usa advisory lock no PostgreSQL para evitar corrida entre múltiplos workers Uvicorn na primeira inicialização.

Para produção, migrações versionadas (Alembic) são preferíveis ao auto-create; o auto-create é apropriado para o harness local e bootstrap inicial.

## Audit

Operações CRUD do control plane geram registros de auditoria com tenant, entidade, ação e detalhes mínimos.
