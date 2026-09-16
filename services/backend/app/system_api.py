from __future__ import annotations

from typing import Any

import httpx
import redis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from .auth import require_auth
from .config import settings
from .control_plane import db_session
from .llm_providers import configured_providers, discover_models
from .qdrant_store import client as qdrant_client
from .schemas import ProcessingOptions

router = APIRouter(tags=["system"])


@router.get("/health", summary="Liveness probe")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": settings.service_name, "version": settings.api_version}


@router.get("/ready", summary="Dependency readiness probe")
def ready() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    ok = True
    try:
        rdb = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        checks["redis"] = bool(rdb.ping())
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}: {exc}"
        ok = False
    try:
        qc = qdrant_client()
        qc.get_collections()
        checks["qdrant"] = True
        checks["qdrant_collection_exists"] = qc.collection_exists(settings.qdrant_collection)
    except Exception as exc:
        checks["qdrant"] = f"error: {type(exc).__name__}: {exc}"
        ok = False
    if settings.control_plane_enabled:
        try:
            with db_session() as db:
                db.execute(text("SELECT 1"))
            checks["postgres"] = True
        except Exception as exc:
            checks["postgres"] = f"error: {type(exc).__name__}: {exc}"
            ok = False
    for name, url in {"parser": f"{settings.parser_url}/health", "embedder": f"{settings.embedder_url}/health"}.items():
        try:
            with httpx.Client(timeout=10.0) as http:
                response = http.get(url)
                response.raise_for_status()
            checks[name] = True
            if name == "parser":
                data = response.json()
                checks["parser_cuda"] = bool(data.get("cuda_available"))
                checks["parser_device"] = data.get("cuda_device") or "CPU"
        except Exception as exc:
            checks[name] = f"error: {type(exc).__name__}: {exc}"
            ok = False
    if not ok:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}


@router.get("/v1/config", dependencies=[Depends(require_auth)], summary="Get effective non-secret runtime configuration")
def config() -> dict[str, Any]:
    return settings.public_dict()


@router.get("/v1/config/chunkers", dependencies=[Depends(require_auth)], summary="Describe the three supported Docling chunkers and their request schemas")
def chunkers() -> dict[str, Any]:
    return {
        "default": settings.chunker_type,
        "types": {
            "hybrid": {
                "best_for": "general RAG; document hierarchy plus token-aware split/merge",
                "fields": {"tokenizer_model": "string", "max_tokens": "integer 32..32768", "merge_peers": "boolean", "repeat_table_header": "boolean", "omit_header_on_overflow": "boolean", "always_emit_headings": "boolean"},
                "example": {"type": "hybrid", "max_tokens": 120, "merge_peers": True, "repeat_table_header": True},
            },
            "hierarchical": {
                "best_for": "maximum preservation of document structure; one chunk per detected element/group",
                "fields": {"merge_list_items": "boolean; retained for upstream compatibility", "always_emit_headings": "boolean"},
                "example": {"type": "hierarchical", "always_emit_headings": False},
            },
            "line_based": {
                "best_for": "tables, source code, logs and line-oriented technical documents",
                "fields": {"tokenizer_model": "string", "max_tokens": "integer 32..32768", "prefix": "string repeated in chunks", "omit_prefix_on_overflow": "boolean"},
                "example": {"type": "line_based", "max_tokens": 120, "prefix": "", "omit_prefix_on_overflow": True},
            },
        },
        "upload_wrapper_example": {"chunking": {"type": "hybrid", "max_tokens": 120}, "pdf": {"do_ocr": True, "do_table_structure": True, "do_cell_matching": True}, "conversion": {"max_num_pages": 1000}, "deduplicate": True},
    }


@router.post("/v1/config/processing-options/validate", dependencies=[Depends(require_auth)], summary="Validate a processing_options object", description="Validates the same processing_options schema accepted by multipart document ingestion. This endpoint exists partly so the complete discriminated chunking union is visible in OpenAPI/Swagger.")
def validate_processing_options(options: ProcessingOptions) -> dict[str, Any]:
    return {"valid": True, "normalized": options.model_dump(mode="json", exclude_none=True), "defaults": settings.public_dict()["chunking_defaults"]}


@router.get("/v1/llm/providers", dependencies=[Depends(require_auth)], summary="List configured LLM providers without exposing secrets")
def llm_providers() -> dict[str, Any]:
    return {"default": settings.llm_provider, "providers": configured_providers()}


@router.get("/v1/llm/providers/{provider}/models", dependencies=[Depends(require_auth)], summary="Discover models from OpenAI-compatible, Ollama, llama.cpp or vLLM servers")
def llm_models(provider: str) -> dict[str, Any]:
    normalized = provider.strip().lower().replace("-", "_")
    if normalized not in {"openai_compatible", "ollama", "llama_cpp", "vllm"}:
        raise HTTPException(400, "Unsupported provider")
    try:
        models = discover_models(normalized)
    except Exception as exc:
        raise HTTPException(503, f"Provider discovery failed: {type(exc).__name__}: {exc}") from exc
    return {"provider": normalized, "models": models, "count": len(models)}
