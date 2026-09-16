from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

LLMProviderName = Literal["openai_compatible", "ollama", "llama_cpp", "vllm"]


class HybridChunkingOptions(BaseModel):
    type: Literal["hybrid"] = "hybrid"
    tokenizer_model: str | None = None
    max_tokens: int | None = Field(default=None, ge=32, le=32768)
    merge_peers: bool | None = None
    repeat_table_header: bool | None = None
    omit_header_on_overflow: bool | None = None
    always_emit_headings: bool | None = None


class HierarchicalChunkingOptions(BaseModel):
    type: Literal["hierarchical"] = "hierarchical"
    merge_list_items: bool | None = Field(
        default=None,
        description="Deprecated upstream by Docling, retained here for compatibility.",
    )
    always_emit_headings: bool | None = None


class LineBasedChunkingOptions(BaseModel):
    type: Literal["line_based"] = "line_based"
    tokenizer_model: str | None = None
    max_tokens: int | None = Field(default=None, ge=32, le=32768)
    prefix: str | None = Field(default=None, max_length=10000)
    omit_prefix_on_overflow: bool | None = None


ChunkingOptions = HybridChunkingOptions | HierarchicalChunkingOptions | LineBasedChunkingOptions


class PdfProcessingOptions(BaseModel):
    do_ocr: bool | None = None
    do_table_structure: bool | None = None
    do_cell_matching: bool | None = None


class ConversionOptions(BaseModel):
    max_num_pages: int | None = Field(default=None, ge=1, le=100000)
    page_range: tuple[int, int] | None = None

    @model_validator(mode="after")
    def validate_page_range(self):
        if self.page_range is not None:
            start, end = self.page_range
            if start < 1 or end < start:
                raise ValueError("page_range must be [start, end] with 1 <= start <= end")
        return self


class ProcessingOptions(BaseModel):
    chunking: ChunkingOptions | None = Field(
        default=None,
        discriminator="type",
        description="Per-document chunking override. Defaults come from environment variables.",
    )
    pdf: PdfProcessingOptions = Field(default_factory=PdfProcessingOptions)
    conversion: ConversionOptions = Field(default_factory=ConversionOptions)
    deduplicate: bool | None = None


class TextIngestRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000_000)
    title: str | None = Field(default=None, max_length=500)
    filename: str | None = Field(default=None, max_length=500)
    corpus_id: str | None = Field(default=None, min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)
    processing_options: ProcessingOptions = Field(default_factory=ProcessingOptions)

    @field_validator("corpus_id")
    @classmethod
    def clean_corpus_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("corpus_id cannot be blank")
        return value


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20000)
    tenant: str | None = Field(default=None, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=128)
    mode: Literal["hybrid", "dense", "sparse"] | None = None
    top_k: int | None = Field(default=None, ge=1)
    limit: int | None = Field(default=None, ge=1)
    candidate_k: int | None = Field(default=None, ge=1)
    score_threshold: float | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    corpora: list[str] = Field(default_factory=list, max_length=100)
    corpus_id: str | None = Field(default=None, max_length=128)
    rerank: bool | None = None
    include_contextualized_text: bool = True

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "limit" in data and ("top_k" not in data or data.get("top_k") is None):
                data["top_k"] = data["limit"]
            if "corpus_id" in data and data.get("corpus_id"):
                c_id = str(data["corpus_id"]).strip()
                corpora = list(data.get("corpora") or [])
                if c_id and c_id not in corpora:
                    corpora.append(c_id)
                data["corpora"] = corpora
            if "tenant" in data and ("tenant_id" not in data or data.get("tenant_id") is None):
                data["tenant_id"] = data["tenant"]
        return data

    @field_validator("corpora")
    @classmethod
    def normalize_corpora(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in value:
            item = item.strip()
            if item and item not in seen:
                seen.add(item)
                out.append(item)
        return out


class GenerationOptions(BaseModel):
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=131072)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    seed: int | None = None
    stop: list[str] | None = Field(default=None, max_length=16)
    top_k: int | None = Field(default=None, ge=0, le=100000)
    min_p: float | None = Field(default=None, ge=0, le=1)
    repetition_penalty: float | None = Field(default=None, gt=0, le=10)
    mirostat: int | None = Field(default=None, ge=0, le=2)
    mirostat_tau: float | None = Field(default=None, gt=0, le=20)
    mirostat_eta: float | None = Field(default=None, gt=0, le=1)
    extra_body: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20000)
    conversation_id: str | None = Field(default=None, max_length=256)
    tenant: str | None = Field(default=None, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=128)
    mode: Literal["hybrid", "dense", "sparse"] | None = None
    top_k: int | None = Field(default=None, ge=1)
    limit: int | None = Field(default=None, ge=1)
    candidate_k: int | None = Field(default=None, ge=1)
    score_threshold: float | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    corpora: list[str] = Field(default_factory=list, max_length=100)
    corpus_id: str | None = Field(default=None, max_length=128)
    rerank: bool | None = None
    system_prompt: str | None = Field(default=None, max_length=30000)
    provider: LLMProviderName | None = None
    model: str | None = Field(default=None, max_length=500)
    generation: GenerationOptions = Field(default_factory=GenerationOptions)
    memory_enabled: bool | None = None
    history_messages: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "limit" in data and ("top_k" not in data or data.get("top_k") is None):
                data["top_k"] = data["limit"]
            if "corpus_id" in data and data.get("corpus_id"):
                c_id = str(data["corpus_id"]).strip()
                corpora = list(data.get("corpora") or [])
                if c_id and c_id not in corpora:
                    corpora.append(c_id)
                data["corpora"] = corpora
            if "tenant" in data and ("tenant_id" not in data or data.get("tenant_id") is None):
                data["tenant_id"] = data["tenant"]
        return data

    @field_validator("corpora")
    @classmethod
    def normalize_corpora(cls, value: list[str]) -> list[str]:
        return SearchRequest.normalize_corpora(value)


class CorpusCreate(BaseModel):
    corpus_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=10000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CorpusUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=10000)
    metadata: dict[str, Any] | None = None


class PromptTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=10000)
    system_prompt: str = Field(min_length=1, max_length=100000)
    model_hint: str | None = Field(default=None, max_length=500)


class PromptTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=10000)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=100000)
    model_hint: str | None = Field(default=None, max_length=500)


class AgentProfileCreate(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=10000)
    provider: LLMProviderName = "openai_compatible"
    model: str | None = Field(default=None, max_length=500)
    prompt_template_id: str | None = Field(default=None, max_length=64)
    corpora: list[str] = Field(default_factory=list, max_length=100)
    retrieval: dict[str, Any] = Field(default_factory=dict)
    generation: GenerationOptions = Field(default_factory=GenerationOptions)
    memory: dict[str, Any] = Field(default_factory=lambda: {"enabled": True})
    welcome_message: str = Field(default="", max_length=10000)
    show_sources: bool = True
    active: bool = True


class AgentProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=10000)
    provider: LLMProviderName | None = None
    model: str | None = Field(default=None, max_length=500)
    prompt_template_id: str | None = Field(default=None, max_length=64)
    corpora: list[str] | None = Field(default=None, max_length=100)
    retrieval: dict[str, Any] | None = None
    generation: GenerationOptions | None = None
    memory: dict[str, Any] | None = None
    welcome_message: str | None = Field(default=None, max_length=10000)
    show_sources: bool | None = None
    active: bool | None = None
