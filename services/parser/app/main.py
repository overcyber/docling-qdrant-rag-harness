from __future__ import annotations

import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator

from docling.chunking import HierarchicalChunker, HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.transforms.chunker.line_chunker import LineBasedTokenChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer

app = FastAPI(title="Docling Parser Service", version="2.0.0")

SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".markdown"}
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "100"))
DEFAULT_CHUNKER_TYPE = os.getenv("CHUNKER_TYPE", "hybrid").strip().lower().replace("-", "_")
DEFAULT_TOKENIZER_MODEL = os.getenv(
    "CHUNK_TOKENIZER_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
DEFAULT_MAX_TOKENS = int(os.getenv("CHUNK_MAX_TOKENS", "120"))
DEFAULT_MAX_NUM_PAGES = int(os.getenv("DOCLING_MAX_NUM_PAGES", "1000"))
FULL_DOCLING_METADATA = os.getenv("PARSER_FULL_DOCLING_METADATA", "false").lower() in {"1", "true", "yes"}


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


class HybridOptions(BaseModel):
    type: Literal["hybrid"] = "hybrid"
    tokenizer_model: str | None = None
    max_tokens: int | None = Field(default=None, ge=32, le=32768)
    merge_peers: bool | None = None
    repeat_table_header: bool | None = None
    omit_header_on_overflow: bool | None = None
    always_emit_headings: bool | None = None


class HierarchicalOptions(BaseModel):
    type: Literal["hierarchical"] = "hierarchical"
    merge_list_items: bool | None = None
    always_emit_headings: bool | None = None


class LineBasedOptions(BaseModel):
    type: Literal["line_based"] = "line_based"
    tokenizer_model: str | None = None
    max_tokens: int | None = Field(default=None, ge=32, le=32768)
    prefix: str | None = Field(default=None, max_length=10000)
    omit_prefix_on_overflow: bool | None = None


ChunkOptions = HybridOptions | HierarchicalOptions | LineBasedOptions


class PdfOptions(BaseModel):
    do_ocr: bool | None = None
    do_table_structure: bool | None = None
    do_cell_matching: bool | None = None


class ConversionOptions(BaseModel):
    max_num_pages: int | None = Field(default=None, ge=1, le=100000)
    page_range: tuple[int, int] | None = None

    @model_validator(mode="after")
    def validate_range(self):
        if self.page_range is not None:
            start, end = self.page_range
            if start < 1 or end < start:
                raise ValueError("page_range must satisfy 1 <= start <= end")
        return self


class ParseOptions(BaseModel):
    chunking: ChunkOptions | None = Field(default=None, discriminator="type")
    pdf: PdfOptions = Field(default_factory=PdfOptions)
    conversion: ConversionOptions = Field(default_factory=ConversionOptions)
    deduplicate: bool | None = None  # accepted for shared API schema; ignored by parser


def default_chunking_dict() -> dict[str, Any]:
    if DEFAULT_CHUNKER_TYPE == "hierarchical":
        return {
            "type": "hierarchical",
            "merge_list_items": env_bool("CHUNK_HIERARCHICAL_MERGE_LIST_ITEMS", True),
            "always_emit_headings": env_bool("CHUNK_HIERARCHICAL_ALWAYS_EMIT_HEADINGS", False),
        }
    if DEFAULT_CHUNKER_TYPE == "line_based":
        return {
            "type": "line_based",
            "tokenizer_model": DEFAULT_TOKENIZER_MODEL,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "prefix": os.getenv("CHUNK_LINE_PREFIX", ""),
            "omit_prefix_on_overflow": env_bool("CHUNK_LINE_OMIT_PREFIX_ON_OVERFLOW", False),
        }
    return {
        "type": "hybrid",
        "tokenizer_model": DEFAULT_TOKENIZER_MODEL,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "merge_peers": env_bool("CHUNK_HYBRID_MERGE_PEERS", True),
        "repeat_table_header": env_bool("CHUNK_HYBRID_REPEAT_TABLE_HEADER", True),
        "omit_header_on_overflow": env_bool("CHUNK_HYBRID_OMIT_HEADER_ON_OVERFLOW", False),
        "always_emit_headings": env_bool("CHUNK_HYBRID_ALWAYS_EMIT_HEADINGS", False),
    }


def effective_options(requested: ParseOptions) -> dict[str, Any]:
    chunking = default_chunking_dict()
    if requested.chunking is not None:
        override = requested.chunking.model_dump(exclude_none=True)
        requested_type = override["type"]
        if requested_type != chunking["type"]:
            # Start from defaults appropriate to the requested type.
            if requested_type == "hybrid":
                chunking = {
                    "type": "hybrid",
                    "tokenizer_model": DEFAULT_TOKENIZER_MODEL,
                    "max_tokens": DEFAULT_MAX_TOKENS,
                    "merge_peers": env_bool("CHUNK_HYBRID_MERGE_PEERS", True),
                    "repeat_table_header": env_bool("CHUNK_HYBRID_REPEAT_TABLE_HEADER", True),
                    "omit_header_on_overflow": env_bool("CHUNK_HYBRID_OMIT_HEADER_ON_OVERFLOW", False),
                    "always_emit_headings": env_bool("CHUNK_HYBRID_ALWAYS_EMIT_HEADINGS", False),
                }
            elif requested_type == "hierarchical":
                chunking = {
                    "type": "hierarchical",
                    "merge_list_items": env_bool("CHUNK_HIERARCHICAL_MERGE_LIST_ITEMS", True),
                    "always_emit_headings": env_bool("CHUNK_HIERARCHICAL_ALWAYS_EMIT_HEADINGS", False),
                }
            else:
                chunking = {
                    "type": "line_based",
                    "tokenizer_model": DEFAULT_TOKENIZER_MODEL,
                    "max_tokens": DEFAULT_MAX_TOKENS,
                    "prefix": os.getenv("CHUNK_LINE_PREFIX", ""),
                    "omit_prefix_on_overflow": env_bool("CHUNK_LINE_OMIT_PREFIX_ON_OVERFLOW", False),
                }
        chunking.update(override)

    pdf = {
        "do_ocr": env_bool("PDF_DO_OCR", True),
        "do_table_structure": env_bool("PDF_DO_TABLE_STRUCTURE", True),
        "do_cell_matching": env_bool("PDF_DO_CELL_MATCHING", True),
    }
    pdf.update(requested.pdf.model_dump(exclude_none=True))

    conversion = {"max_num_pages": DEFAULT_MAX_NUM_PAGES, "page_range": None}
    conversion.update(requested.conversion.model_dump(exclude_none=True))
    return {"chunking": chunking, "pdf": pdf, "conversion": conversion}


@lru_cache(maxsize=8)
def get_tokenizer(model_name: str, max_tokens: int) -> HuggingFaceTokenizer:
    hf = AutoTokenizer.from_pretrained(model_name)
    return HuggingFaceTokenizer(tokenizer=hf, max_tokens=max_tokens)


@lru_cache(maxsize=16)
def get_converter(do_ocr: bool, do_table_structure: bool, do_cell_matching: bool) -> DocumentConverter:
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = do_ocr
    pipeline_options.do_table_structure = do_table_structure
    pipeline_options.table_structure_options.do_cell_matching = do_cell_matching
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


def get_chunker(config: dict[str, Any]):
    kind = config["type"]
    if kind == "hierarchical":
        return HierarchicalChunker(
            merge_list_items=bool(config.get("merge_list_items", True)),
            always_emit_headings=bool(config.get("always_emit_headings", False)),
        )

    tokenizer = get_tokenizer(
        str(config.get("tokenizer_model") or DEFAULT_TOKENIZER_MODEL),
        int(config.get("max_tokens") or DEFAULT_MAX_TOKENS),
    )
    if kind == "line_based":
        return LineBasedTokenChunker(
            tokenizer=tokenizer,
            prefix=str(config.get("prefix") or ""),
            omit_prefix_on_overflow=bool(config.get("omit_prefix_on_overflow", False)),
        )
    return HybridChunker(
        tokenizer=tokenizer,
        merge_peers=bool(config.get("merge_peers", True)),
        repeat_table_header=bool(config.get("repeat_table_header", True)),
        omit_header_on_overflow=bool(config.get("omit_header_on_overflow", False)),
        always_emit_headings=bool(config.get("always_emit_headings", False)),
    )


def safe_pages(chunk: Any) -> list[int]:
    pages: set[int] = set()
    try:
        for item in chunk.meta.doc_items:
            for prov in item.prov:
                page_no = getattr(prov, "page_no", None)
                if page_no is not None:
                    pages.add(int(page_no))
    except Exception:
        pass
    return sorted(pages)


def compact_docling_meta(chunk: Any) -> dict[str, Any]:
    if FULL_DOCLING_METADATA:
        try:
            return chunk.meta.export_json_dict()
        except Exception:
            try:
                return chunk.meta.model_dump(mode="json")
            except Exception:
                return {}

    labels: list[str] = []
    try:
        for item in chunk.meta.doc_items:
            label = getattr(item, "label", None)
            if label is not None:
                labels.append(str(label))
    except Exception:
        pass
    return {
        "headings": list(getattr(chunk.meta, "headings", None) or []),
        "doc_items_count": len(getattr(chunk.meta, "doc_items", None) or []),
        "labels": sorted(set(labels))[:64],
    }


def fallback_text_chunks(text: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    max_tokens = int(config.get("max_tokens") or DEFAULT_MAX_TOKENS)
    char_budget = max(512, max_tokens * 4)
    kind = config["type"]
    units = text.splitlines(keepends=True) if kind == "line_based" else [p + "\n\n" for p in text.split("\n\n")]
    units = [u for u in units if u.strip()] or [text]
    chunks: list[dict[str, Any]] = []
    current = ""
    for unit in units:
        if current and len(current) + len(unit) > char_budget:
            chunks.append({
                "text": current.strip(),
                "contextualized_text": current.strip(),
                "metadata": {
                    "headings": [], "pages": [], "page_provenance": "none",
                    "docling": {}, "fallback": True,
                },
            })
            current = ""
        current += unit
    if current.strip():
        chunks.append({
            "text": current.strip(),
            "contextualized_text": current.strip(),
            "metadata": {
                "headings": [], "pages": [], "page_provenance": "none",
                "docling": {}, "fallback": True,
            },
        })
    return chunks


def parse_options(raw: str | None) -> ParseOptions:
    if not raw:
        return ParseOptions()
    try:
        return ParseOptions.model_validate(json.loads(raw))
    except Exception as exc:
        raise HTTPException(400, f"Invalid parser options: {exc}") from exc


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "parser-docling",
        "default_chunker_type": DEFAULT_CHUNKER_TYPE,
        "tokenizer_model": DEFAULT_TOKENIZER_MODEL,
        "chunk_max_tokens": DEFAULT_MAX_TOKENS,
        "full_docling_metadata": FULL_DOCLING_METADATA,
    }


@app.post("/parse")
async def parse(
    file: UploadFile = File(...),
    options: str | None = Form(default=None),
) -> dict[str, Any]:
    suffix = Path(file.filename or "document").suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(415, f"Unsupported extension: {suffix}")

    requested = parse_options(options)
    effective = effective_options(requested)
    chunking_config = effective["chunking"]
    tmp_path: Path | None = None

    try:
        size = 0
        limit = MAX_FILE_MB * 1024 * 1024
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            while True:
                block = await file.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                if size > limit:
                    raise HTTPException(413, f"File exceeds {MAX_FILE_MB} MB")
                tmp.write(block)

        try:
            pdf = effective["pdf"]
            converter = get_converter(
                bool(pdf["do_ocr"]),
                bool(pdf["do_table_structure"]),
                bool(pdf["do_cell_matching"]),
            )
            convert_kwargs: dict[str, Any] = {
                "source": tmp_path,
                "max_num_pages": int(effective["conversion"]["max_num_pages"]),
            }
            if effective["conversion"].get("page_range") is not None:
                convert_kwargs["page_range"] = tuple(effective["conversion"]["page_range"])

            result = converter.convert(**convert_kwargs)
            doc = result.document
            chunker = get_chunker(chunking_config)
            out: list[dict[str, Any]] = []
            is_line_based = chunking_config["type"] == "line_based"

            for i, chunk in enumerate(chunker.chunk(dl_doc=doc)):
                headings = list(getattr(chunk.meta, "headings", None) or [])
                pages = safe_pages(chunk)
                out.append({
                    "index": i,
                    "text": chunk.text,
                    "contextualized_text": chunker.contextualize(chunk=chunk),
                    "metadata": {
                        "headings": headings,
                        "pages": pages,
                        "page_provenance": "document" if is_line_based else "chunk",
                        "docling": compact_docling_meta(chunk),
                        "fallback": False,
                    },
                })

            if not out:
                raise RuntimeError("Docling produced zero chunks")
            return {
                "filename": file.filename,
                "chunks": out,
                "chunk_count": len(out),
                "chunker_type": chunking_config["type"],
                "chunking_config": chunking_config,
                "processing_options": effective,
            }
        except Exception as exc:
            if suffix in {".txt", ".md", ".markdown"}:
                text = tmp_path.read_text(encoding="utf-8", errors="replace")
                chunks = fallback_text_chunks(text, chunking_config)
                return {
                    "filename": file.filename,
                    "chunks": [{"index": i, **c} for i, c in enumerate(chunks)],
                    "chunk_count": len(chunks),
                    "chunker_type": chunking_config["type"],
                    "chunking_config": chunking_config,
                    "processing_options": effective,
                    "warning": f"Docling failed; text fallback used: {type(exc).__name__}: {exc}",
                }
            raise
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Parsing failed: {type(exc).__name__}: {exc}") from exc
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)
