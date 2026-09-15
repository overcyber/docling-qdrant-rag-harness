from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String, Text, UniqueConstraint, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Corpus(Base):
    __tablename__ = "rag_corpora"
    __table_args__ = (UniqueConstraint("tenant_id", "corpus_id", name="uq_corpus_tenant_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(256), index=True)
    corpus_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PromptTemplate(Base):
    __tablename__ = "rag_prompt_templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(256), index=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text)
    model_hint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentProfile(Base):
    __tablename__ = "rag_agent_profiles"
    __table_args__ = (UniqueConstraint("tenant_id", "agent_id", name="uq_agent_tenant_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(256), index=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(64), default="openai_compatible")
    model: Mapped[str | None] = mapped_column(String(500), nullable=True)
    prompt_template_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    corpora: Mapped[list[str]] = mapped_column(JSON, default=list)
    retrieval: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    memory: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    welcome_message: Mapped[str] = mapped_column(Text, default="")
    show_sources: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditEvent(Base):
    __tablename__ = "rag_audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(256), index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(256), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


@lru_cache(maxsize=1)
def engine():
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def session_factory():
    return sessionmaker(bind=engine(), expire_on_commit=False, class_=Session)


def init_control_plane() -> None:
    if not (settings.control_plane_enabled and settings.control_plane_auto_create):
        return
    eng = engine()
    # Multiple Uvicorn workers may start simultaneously. A PostgreSQL advisory lock
    # makes create_all deterministic instead of racing on first boot.
    with eng.begin() as conn:
        is_postgres = eng.dialect.name == "postgresql"
        if is_postgres:
            conn.execute(text("SELECT pg_advisory_lock(74192021)"))
        try:
            Base.metadata.create_all(bind=conn)
        finally:
            if is_postgres:
                conn.execute(text("SELECT pg_advisory_unlock(74192021)"))


def db_session() -> Session:
    if not settings.control_plane_enabled:
        raise RuntimeError("Control plane is disabled")
    return session_factory()()


def audit(db: Session, tenant: str, action: str, entity_type: str, entity_id: str, details: dict[str, Any] | None = None) -> None:
    db.add(AuditEvent(tenant_id=tenant, action=action, entity_type=entity_type, entity_id=entity_id, details=details or {}))


def model_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Corpus):
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "corpus_id": row.corpus_id,
            "name": row.name,
            "description": row.description,
            "metadata": row.metadata_json or {},
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    if isinstance(row, PromptTemplate):
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "description": row.description,
            "system_prompt": row.system_prompt,
            "model_hint": row.model_hint,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    if isinstance(row, AgentProfile):
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "agent_id": row.agent_id,
            "name": row.name,
            "description": row.description,
            "provider": row.provider,
            "model": row.model,
            "prompt_template_id": row.prompt_template_id,
            "corpora": row.corpora or [],
            "retrieval": row.retrieval or {},
            "generation": row.generation or {},
            "memory": row.memory or {},
            "welcome_message": row.welcome_message,
            "show_sources": row.show_sources,
            "active": row.active,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    raise TypeError(type(row))


def get_corpus(db: Session, tenant: str, corpus_id: str) -> Corpus | None:
    return db.scalar(select(Corpus).where(Corpus.tenant_id == tenant, Corpus.corpus_id == corpus_id))


def get_prompt(db: Session, tenant: str, template_id: str) -> PromptTemplate | None:
    return db.scalar(select(PromptTemplate).where(PromptTemplate.tenant_id == tenant, PromptTemplate.id == template_id))


def get_agent(db: Session, tenant: str, agent_id: str) -> AgentProfile | None:
    return db.scalar(select(AgentProfile).where(AgentProfile.tenant_id == tenant, AgentProfile.agent_id == agent_id))
