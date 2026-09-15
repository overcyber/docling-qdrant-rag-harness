from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20000)
    mode: Literal["hybrid", "dense", "sparse"] | None = None
    top_k: int | None = Field(default=None, ge=1)
    candidate_k: int | None = Field(default=None, ge=1)
    score_threshold: float | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    rerank: bool | None = None
    include_contextualized_text: bool = True


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20000)
    conversation_id: str | None = Field(default=None, max_length=256)
    mode: Literal["hybrid", "dense", "sparse"] | None = None
    top_k: int | None = Field(default=None, ge=1)
    candidate_k: int | None = Field(default=None, ge=1)
    score_threshold: float | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    rerank: bool | None = None
    system_prompt: str | None = Field(default=None, max_length=30000)
