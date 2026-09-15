# Agent integration

The harness is deliberately usable as a retrieval tool without coupling the agent to a specific framework.

## Pattern A — external agent owns generation

Recommended for sophisticated agents.

```text
Agent
  -> POST /v1/rag/context
  <- evidence + structured sources
  -> agent policy/tool loop
  -> agent's own LLM
```

Advantages:

- the agent controls context budgeting;
- the agent can combine document RAG with other tools;
- the harness remains model-agnostic;
- source provenance is available before generation.

## Pattern B — harness performs generation

```text
Agent/UI
  -> POST /v1/rag/chat
  -> retrieval
  -> Redis conversation memory
  -> OpenAI-compatible LLM
  <- answer + sources
```

## Grounding contract

Every source uses a stable response-local citation tag:

```json
{
  "citation": "S1",
  "document_id": "...",
  "filename": "report.pdf",
  "pages": [12],
  "headings": ["Results", "Evaluation"],
  "text": "..."
}
```

Generation prompts instruct the LLM to cite `[S1]`, `[S2]`, etc. The caller should still validate that every citation tag in an answer exists in the returned `sources` array before displaying it as grounded output.

## Prompt-injection boundary

Retrieved documents are untrusted input. The built-in system prompt explicitly tells the LLM not to treat retrieved text as instructions. For higher assurance, add application-side policy checks and avoid granting high-impact tools solely on the basis of retrieved content.

## Metadata filtering

Example:

```json
{
  "query": "minimum password length",
  "filters": {
    "department": "security",
    "classification": "internal"
  }
}
```

Unknown metadata keys map to `user_metadata.<key>`.
