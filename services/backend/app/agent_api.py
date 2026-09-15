from __future__ import annotations

from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .auth import require_auth, tenant_id
from .control_plane import (
    AgentProfile,
    Corpus,
    PromptTemplate,
    audit,
    db_session,
    get_agent,
    get_corpus,
    get_prompt,
    model_dict,
)
from .rag_api import chat_impl, stream_chat_events
from .schemas import (
    AgentProfileCreate,
    AgentProfileUpdate,
    ChatRequest,
    CorpusCreate,
    CorpusUpdate,
    GenerationOptions,
    PromptTemplateCreate,
    PromptTemplateUpdate,
)

router = APIRouter(prefix="/v1", tags=["agents"], dependencies=[Depends(require_auth)])


def _db_error(exc: Exception) -> HTTPException:
    return HTTPException(503, f"Control plane unavailable: {type(exc).__name__}: {exc}")


@router.post("/corpora", status_code=status.HTTP_201_CREATED, summary="Register a logical corpus")
def create_corpus(req: CorpusCreate, tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            row = Corpus(
                tenant_id=tenant,
                corpus_id=req.corpus_id,
                name=req.name,
                description=req.description,
                metadata_json=req.metadata,
            )
            db.add(row)
            audit(db, tenant, "create", "corpus", req.corpus_id)
            db.commit()
            return model_dict(row)
    except IntegrityError as exc:
        raise HTTPException(409, "corpus_id already exists for this tenant") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc


@router.get("/corpora", summary="List corpus registry entries")
def list_corpora(tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            rows = db.scalars(select(Corpus).where(Corpus.tenant_id == tenant).order_by(Corpus.corpus_id)).all()
            return {"items": [model_dict(x) for x in rows]}
    except Exception as exc:
        raise _db_error(exc) from exc


@router.get("/corpora/{corpus_id}", summary="Get one corpus registry entry")
def read_corpus(corpus_id: str, tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            row = get_corpus(db, tenant, corpus_id)
            if not row:
                raise HTTPException(404, "Corpus not found")
            return model_dict(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc


@router.put("/corpora/{corpus_id}", summary="Update a corpus registry entry")
def update_corpus(corpus_id: str, req: CorpusUpdate, tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            row = get_corpus(db, tenant, corpus_id)
            if not row:
                raise HTTPException(404, "Corpus not found")
            changes = req.model_dump(exclude_unset=True)
            if "metadata" in changes:
                row.metadata_json = changes.pop("metadata")
            for key, value in changes.items():
                setattr(row, key, value)
            audit(db, tenant, "update", "corpus", corpus_id, {"fields": list(changes)})
            db.commit()
            return model_dict(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc


@router.delete("/corpora/{corpus_id}", summary="Delete only the corpus registry entry; vectors are unchanged")
def delete_corpus_registry(corpus_id: str, tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            row = get_corpus(db, tenant, corpus_id)
            if not row:
                raise HTTPException(404, "Corpus not found")
            db.delete(row)
            audit(db, tenant, "delete", "corpus", corpus_id)
            db.commit()
            return {"status": "deleted", "corpus_id": corpus_id, "vectors_deleted": False}
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc


@router.post("/prompt-templates", status_code=status.HTTP_201_CREATED, summary="Create a durable system-prompt template")
def create_prompt_template(req: PromptTemplateCreate, tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            row = PromptTemplate(tenant_id=tenant, **req.model_dump())
            db.add(row)
            db.flush()
            audit(db, tenant, "create", "prompt_template", row.id)
            db.commit()
            return model_dict(row)
    except Exception as exc:
        raise _db_error(exc) from exc


@router.get("/prompt-templates", summary="List prompt templates")
def list_prompt_templates(tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            rows = db.scalars(
                select(PromptTemplate).where(PromptTemplate.tenant_id == tenant).order_by(PromptTemplate.name)
            ).all()
            return {"items": [model_dict(x) for x in rows]}
    except Exception as exc:
        raise _db_error(exc) from exc


@router.get("/prompt-templates/{template_id}", summary="Get one prompt template")
def read_prompt_template(template_id: str, tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            row = get_prompt(db, tenant, template_id)
            if not row:
                raise HTTPException(404, "Prompt template not found")
            return model_dict(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc


@router.put("/prompt-templates/{template_id}", summary="Update a prompt template")
def update_prompt_template(template_id: str, req: PromptTemplateUpdate, tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            row = get_prompt(db, tenant, template_id)
            if not row:
                raise HTTPException(404, "Prompt template not found")
            changes = req.model_dump(exclude_unset=True)
            for key, value in changes.items():
                setattr(row, key, value)
            audit(db, tenant, "update", "prompt_template", template_id, {"fields": list(changes)})
            db.commit()
            return model_dict(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc


@router.delete("/prompt-templates/{template_id}", summary="Delete a prompt template")
def delete_prompt_template(template_id: str, tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            row = get_prompt(db, tenant, template_id)
            if not row:
                raise HTTPException(404, "Prompt template not found")
            db.delete(row)
            audit(db, tenant, "delete", "prompt_template", template_id)
            db.commit()
            return {"status": "deleted", "id": template_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc


@router.post("/agents", status_code=status.HTTP_201_CREATED, summary="Create an agent profile")
def create_agent(req: AgentProfileCreate, tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            if req.prompt_template_id and not get_prompt(db, tenant, req.prompt_template_id):
                raise HTTPException(400, "prompt_template_id does not exist for this tenant")
            data = req.model_dump(mode="json")
            data["generation"] = req.generation.model_dump(mode="json", exclude_none=True)
            row = AgentProfile(tenant_id=tenant, **data)
            db.add(row)
            audit(db, tenant, "create", "agent", req.agent_id)
            db.commit()
            return model_dict(row)
    except IntegrityError as exc:
        raise HTTPException(409, "agent_id already exists for this tenant") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc


@router.get("/agents", summary="List agent profiles")
def list_agents(tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            rows = db.scalars(
                select(AgentProfile).where(AgentProfile.tenant_id == tenant).order_by(AgentProfile.agent_id)
            ).all()
            return {"items": [model_dict(x) for x in rows]}
    except Exception as exc:
        raise _db_error(exc) from exc


@router.get("/agents/{agent_id}", summary="Get one agent profile")
def read_agent(agent_id: str, tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            row = get_agent(db, tenant, agent_id)
            if not row:
                raise HTTPException(404, "Agent not found")
            return model_dict(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc


@router.put("/agents/{agent_id}", summary="Update an agent profile")
def update_agent(agent_id: str, req: AgentProfileUpdate, tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            row = get_agent(db, tenant, agent_id)
            if not row:
                raise HTTPException(404, "Agent not found")
            changes = req.model_dump(mode="json", exclude_unset=True)
            if "prompt_template_id" in changes and changes["prompt_template_id"]:
                if not get_prompt(db, tenant, changes["prompt_template_id"]):
                    raise HTTPException(400, "prompt_template_id does not exist for this tenant")
            if req.generation is not None:
                changes["generation"] = req.generation.model_dump(mode="json", exclude_none=True)
            for key, value in changes.items():
                setattr(row, key, value)
            audit(db, tenant, "update", "agent", agent_id, {"fields": list(changes)})
            db.commit()
            return model_dict(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc


@router.delete("/agents/{agent_id}", summary="Delete an agent profile")
def delete_agent(agent_id: str, tenant: str = Depends(tenant_id)):
    try:
        with db_session() as db:
            row = get_agent(db, tenant, agent_id)
            if not row:
                raise HTTPException(404, "Agent not found")
            db.delete(row)
            audit(db, tenant, "delete", "agent", agent_id)
            db.commit()
            return {"status": "deleted", "agent_id": agent_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc


def _agent_request(agent_id: str, incoming: ChatRequest, tenant: str) -> tuple[ChatRequest, bool]:
    try:
        with db_session() as db:
            row = get_agent(db, tenant, agent_id)
            if not row or not row.active:
                raise HTTPException(404, "Active agent not found")
            prompt = get_prompt(db, tenant, row.prompt_template_id) if row.prompt_template_id else None
            retrieval = row.retrieval or {}
            profile_generation = dict(row.generation or {})
            request_generation = incoming.generation.model_dump(mode="json", exclude_none=True)
            profile_extra = dict(profile_generation.pop("extra_body", {}) or {})
            request_extra = dict(request_generation.pop("extra_body", {}) or {})
            generation = {**profile_generation, **request_generation, "extra_body": {**profile_extra, **request_extra}}
            req = ChatRequest(
                question=incoming.question,
                conversation_id=incoming.conversation_id,
                mode=incoming.mode or retrieval.get("mode"),
                top_k=incoming.top_k or retrieval.get("top_k"),
                candidate_k=incoming.candidate_k or retrieval.get("candidate_k"),
                score_threshold=(incoming.score_threshold if incoming.score_threshold is not None else retrieval.get("score_threshold")),
                filters={**(retrieval.get("filters") or {}), **incoming.filters},
                corpora=incoming.corpora or list(row.corpora or []),
                rerank=incoming.rerank if incoming.rerank is not None else retrieval.get("rerank"),
                system_prompt=incoming.system_prompt or (prompt.system_prompt if prompt else None),
                provider=incoming.provider or row.provider,
                model=incoming.model or row.model or (prompt.model_hint if prompt else None),
                generation=GenerationOptions.model_validate(generation),
                memory_enabled=(incoming.memory_enabled if incoming.memory_enabled is not None else bool((row.memory or {}).get("enabled", True))),
                history_messages=(incoming.history_messages if incoming.history_messages is not None else (row.memory or {}).get("max_messages")),
            )
            return req, bool(row.show_sources)
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc


@router.post("/agents/{agent_id}/chat", summary="Chat using a durable agent profile")
def agent_chat(agent_id: str, req: ChatRequest, tenant: str = Depends(tenant_id)):
    effective, show_sources = _agent_request(agent_id, req, tenant)
    result = chat_impl(effective, tenant)
    result["agent_id"] = agent_id
    if not show_sources:
        result["sources"] = []
    return result


@router.post("/agents/{agent_id}/chat/stream", summary="Stream chat using a durable agent profile")
def agent_chat_stream(agent_id: str, req: ChatRequest, tenant: str = Depends(tenant_id)):
    effective, show_sources = _agent_request(agent_id, req, tenant)

    def events() -> Iterator[str]:
        for event in stream_chat_events(effective, tenant):
            if not show_sources and event.startswith("event: source\n"):
                continue
            yield event

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Agent-ID": agent_id},
    )
