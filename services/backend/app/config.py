from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the public API, worker and RAG stack.

    All fields can be configured with environment variables using their upper-case
    names. Comma-separated values are accepted for list-like settings.
    """

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False, env_ignore_empty=True)

    # Service / FastAPI
    service_name: str = "api"
    api_title: str = "Docling Qdrant Advanced RAG Harness"
    api_description: str = (
        "Unified document ingestion and advanced RAG API backed by Docling, "
        "Qdrant, Redis and Celery."
    )
    api_version: str = "2.1.0"
    api_docs_enabled: bool = True
    api_docs_url: str = "/docs"
    api_redoc_url: str = "/redoc"
    api_openapi_url: str = "/openapi.json"
    api_root_path: str = ""
    api_public_base_url: str = ""
    api_allowed_hosts: list[str] = Field(default_factory=lambda: ["*"])
    api_cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    api_cors_allow_credentials: bool = False
    api_cors_allow_methods: list[str] = Field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    api_cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])
    api_max_batch_files: int = 100
    api_upload_buffer_mb: int = 1

    # Authentication / tenancy
    api_key: str = ""
    tenant_header_name: str = "X-Tenant-ID"
    default_tenant_id: str = "default"

    # Durable control plane (agent profiles, prompt templates, corpus registry, audit)
    control_plane_enabled: bool = True
    control_plane_auto_create: bool = True
    database_url: str = "postgresql+psycopg://rag:rag@postgres:5432/rag"
    default_corpus_id: str = "default"

    # Optional NATS event bus. Celery remains the authoritative work queue.
    nats_enabled: bool = False
    nats_url: str = "nats://nats:4222"
    nats_subject_prefix: str = "rag"

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    celery_visibility_timeout: int = 7200
    celery_result_expires: int = 604800
    job_owner_ttl_seconds: int = 604800
    dedupe_pending_ttl_seconds: int = 7200

    # Qdrant
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "documents_v2"
    qdrant_metadata_index_fields: list[str] = Field(default_factory=list)
    embedding_dim: int = 384
    dense_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    sparse_model: str = "Qdrant/bm25"
    bm25_language: str = "portuguese"

    # Internal services
    parser_url: str = "http://parser-docling:8001"
    embedder_url: str = "http://embedder:8002"
    parser_timeout_seconds: int = 1800
    embedder_timeout_seconds: int = 900
    embedding_batch_size: int = 32

    # Upload / ingestion
    upload_dir: str = "/data/uploads"
    max_file_mb: int = 100
    delete_source_after_ingest: bool = False
    default_deduplicate: bool = True

    # Default Docling processing options (may be overridden per upload)
    chunker_type: str = "hybrid"
    chunk_tokenizer_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    chunk_max_tokens: int = 120
    chunk_hybrid_merge_peers: bool = True
    chunk_hybrid_repeat_table_header: bool = True
    chunk_hybrid_omit_header_on_overflow: bool = False
    chunk_hybrid_always_emit_headings: bool = False
    chunk_hierarchical_merge_list_items: bool = True
    chunk_hierarchical_always_emit_headings: bool = False
    chunk_line_prefix: str = ""
    chunk_line_omit_prefix_on_overflow: bool = False
    pdf_do_ocr: bool = True
    pdf_do_table_structure: bool = True
    pdf_do_cell_matching: bool = True
    docling_max_num_pages: int = 1000
    parser_full_docling_metadata: bool = False

    # Retrieval
    retrieval_mode: str = "hybrid"
    default_top_k: int = 8
    default_candidate_k: int = 40
    max_top_k: int = 50
    max_candidate_k: int = 200
    default_score_threshold: float | None = None
    reranker_enabled: bool = False

    # Chat / agent harness
    chat_memory_ttl_seconds: int = 86400
    chat_history_messages: int = 8
    max_context_chars: int = 60000

    # LLM providers. Provider-specific adapters preserve native capabilities.
    llm_provider: str = "openai_compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    ollama_base_url: str = "http://ollama:11434"
    ollama_api_key: str = ""
    ollama_model: str = ""

    llama_cpp_base_url: str = "http://llama-cpp:8080/v1"
    llama_cpp_api_key: str = ""
    llama_cpp_model: str = ""

    vllm_base_url: str = "http://vllm:8000/v1"
    vllm_api_key: str = ""
    vllm_model: str = ""

    llm_temperature: float = 0.1
    llm_top_p: float = 0.9
    llm_max_tokens: int = 2048
    llm_presence_penalty: float = 0.0
    llm_frequency_penalty: float = 0.0
    llm_timeout_seconds: int = 120

    @field_validator(
        "api_allowed_hosts",
        "api_cors_origins",
        "api_cors_allow_methods",
        "api_cors_allow_headers",
        "qdrant_metadata_index_fields",
        mode="before",
    )
    @classmethod
    def split_csv(cls, value: Any):
        if value is None:
            return []
        if isinstance(value, str):
            return [x.strip() for x in value.split(",") if x.strip()]
        return value

    @field_validator("chunker_type")
    @classmethod
    def validate_chunker_type(cls, value: str) -> str:
        value = value.strip().lower().replace("-", "_")
        if value not in {"hybrid", "hierarchical", "line_based"}:
            raise ValueError("CHUNKER_TYPE must be hybrid, hierarchical or line_based")
        return value

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        value = value.strip().lower().replace("-", "_")
        if value not in {"openai_compatible", "ollama", "llama_cpp", "vllm"}:
            raise ValueError("LLM_PROVIDER must be openai_compatible, ollama, llama_cpp or vllm")
        return value

    @field_validator("retrieval_mode")
    @classmethod
    def validate_retrieval_mode(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"hybrid", "dense", "sparse"}:
            raise ValueError("RETRIEVAL_MODE must be hybrid, dense or sparse")
        return value

    def public_dict(self) -> dict[str, Any]:
        """Safe configuration view for the /v1/config endpoint."""
        return {
            "api": {
                "title": self.api_title,
                "version": self.api_version,
                "docs_enabled": self.api_docs_enabled,
                "docs_url": self.api_docs_url if self.api_docs_enabled else None,
                "redoc_url": self.api_redoc_url if self.api_docs_enabled else None,
                "openapi_url": self.api_openapi_url if self.api_docs_enabled else None,
                "root_path": self.api_root_path,
                "max_batch_files": self.api_max_batch_files,
                "max_file_mb": self.max_file_mb,
                "authentication_enabled": bool(self.api_key),
                "tenant_header_name": self.tenant_header_name,
                "job_owner_ttl_seconds": self.job_owner_ttl_seconds,
                "dedupe_pending_ttl_seconds": self.dedupe_pending_ttl_seconds,
            },
            "chunking_defaults": {
                "type": self.chunker_type,
                "tokenizer_model": self.chunk_tokenizer_model,
                "max_tokens": self.chunk_max_tokens,
                "hybrid": {
                    "merge_peers": self.chunk_hybrid_merge_peers,
                    "repeat_table_header": self.chunk_hybrid_repeat_table_header,
                    "omit_header_on_overflow": self.chunk_hybrid_omit_header_on_overflow,
                    "always_emit_headings": self.chunk_hybrid_always_emit_headings,
                },
                "hierarchical": {
                    "merge_list_items": self.chunk_hierarchical_merge_list_items,
                    "always_emit_headings": self.chunk_hierarchical_always_emit_headings,
                },
                "line_based": {
                    "prefix": self.chunk_line_prefix,
                    "omit_prefix_on_overflow": self.chunk_line_omit_prefix_on_overflow,
                },
            },
            "docling_defaults": {
                "pdf_do_ocr": self.pdf_do_ocr,
                "pdf_do_table_structure": self.pdf_do_table_structure,
                "pdf_do_cell_matching": self.pdf_do_cell_matching,
                "max_num_pages": self.docling_max_num_pages,
            },
            "retrieval_defaults": {
                "mode": self.retrieval_mode,
                "top_k": self.default_top_k,
                "candidate_k": self.default_candidate_k,
                "max_top_k": self.max_top_k,
                "max_candidate_k": self.max_candidate_k,
                "score_threshold": self.default_score_threshold,
                "reranker_enabled": self.reranker_enabled,
            },
            "control_plane": {
                "enabled": self.control_plane_enabled,
                "auto_create": self.control_plane_auto_create,
                "default_corpus_id": self.default_corpus_id,
                "nats_enabled": self.nats_enabled,
            },
            "models": {
                "dense_model": self.dense_model,
                "sparse_model": self.sparse_model,
                "bm25_language": self.bm25_language,
                "embedding_dim_fallback": self.embedding_dim,
                "llm_provider": self.llm_provider,
                "providers": {
                    "openai_compatible": {"configured": bool(self.llm_base_url), "model_configured": bool(self.llm_model), "base_url": self.llm_base_url, "model": self.llm_model},
                    "ollama": {"configured": bool(self.ollama_base_url), "model_configured": bool(self.ollama_model), "base_url": self.ollama_base_url, "model": self.ollama_model},
                    "llama_cpp": {"configured": bool(self.llama_cpp_base_url), "model_configured": bool(self.llama_cpp_model), "base_url": self.llama_cpp_base_url, "model": self.llama_cpp_model},
                    "vllm": {"configured": bool(self.vllm_base_url), "model_configured": bool(self.vllm_model), "base_url": self.vllm_base_url, "model": self.vllm_model},
                },
            },
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
