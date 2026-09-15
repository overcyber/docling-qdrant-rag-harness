from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .config import settings
from .ingestion_api import router as ingestion_router
from .rag_api import router as rag_router
from .system_api import router as system_router

TAGS_METADATA = [
    {
        "name": "documents",
        "description": "Asynchronous ingestion, status inspection and document lifecycle operations.",
    },
    {
        "name": "rag",
        "description": "Dense, sparse and hybrid retrieval, context assembly and optional RAG generation.",
    },
    {
        "name": "system",
        "description": "Health, readiness and safe runtime configuration introspection.",
    },
]

servers = [{"url": settings.api_public_base_url}] if settings.api_public_base_url else None

app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    docs_url=settings.api_docs_url if settings.api_docs_enabled else None,
    redoc_url=settings.api_redoc_url if settings.api_docs_enabled else None,
    openapi_url=settings.api_openapi_url if settings.api_docs_enabled else None,
    root_path=settings.api_root_path,
    servers=servers,
    openapi_tags=TAGS_METADATA,
    contact={"name": "RAG Harness Operator"},
    license_info={"name": "Project-specific; see repository LICENSE if present"},
)

if settings.api_allowed_hosts and settings.api_allowed_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.api_allowed_hosts)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=settings.api_cors_allow_credentials,
    allow_methods=settings.api_cors_allow_methods,
    allow_headers=settings.api_cors_allow_headers,
)

app.include_router(system_router)
app.include_router(ingestion_router)
app.include_router(rag_router)
