import os
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

app = FastAPI(title="Embedding Service", version="1.0.0")

DENSE_MODEL = os.getenv(
    "DENSE_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
SPARSE_MODEL = os.getenv("SPARSE_MODEL", "Qdrant/bm25")
BM25_LANGUAGE = os.getenv("BM25_LANGUAGE", "portuguese")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "false").lower() in {"1", "true", "yes"}
BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
CACHE_DIR = os.getenv("FASTEMBED_CACHE_PATH", "/models/fastembed")


class DocumentsRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=512)


class QueryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class RerankRequest(BaseModel):
    query: str = Field(min_length=1)
    documents: list[str] = Field(min_length=1, max_length=200)


@lru_cache(maxsize=1)
def dense_model() -> TextEmbedding:
    return TextEmbedding(model_name=DENSE_MODEL, cache_dir=CACHE_DIR)


@lru_cache(maxsize=1)
def sparse_model() -> SparseTextEmbedding:
    return SparseTextEmbedding(model_name=SPARSE_MODEL, cache_dir=CACHE_DIR, language=BM25_LANGUAGE)


@lru_cache(maxsize=1)
def reranker_model() -> TextCrossEncoder:
    if not RERANKER_ENABLED:
        raise RuntimeError("Reranker is disabled")
    return TextCrossEncoder(model_name=RERANKER_MODEL, cache_dir=CACHE_DIR)


def sparse_to_json(item: Any) -> dict[str, list]:
    return {
        "indices": [int(x) for x in item.indices.tolist()],
        "values": [float(x) for x in item.values.tolist()],
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "embedder",
        "dense_model": DENSE_MODEL,
        "sparse_model": SPARSE_MODEL,
        "bm25_language": BM25_LANGUAGE,
        "reranker_enabled": RERANKER_ENABLED,
        "reranker_model": RERANKER_MODEL if RERANKER_ENABLED else None,
    }


@app.post("/embed/documents")
def embed_documents(req: DocumentsRequest) -> dict[str, Any]:
    try:
        dense = list(dense_model().passage_embed(req.texts, batch_size=BATCH_SIZE))
        sparse = list(sparse_model().embed(req.texts, batch_size=BATCH_SIZE))
        return {
            "dense": [[float(v) for v in arr.tolist()] for arr in dense],
            "sparse": [sparse_to_json(x) for x in sparse],
            "model": DENSE_MODEL,
            "models": {
                "dense": DENSE_MODEL,
                "sparse": SPARSE_MODEL,
                "bm25_language": BM25_LANGUAGE,
            },
        }
    except Exception as exc:
        raise HTTPException(500, f"Embedding failed: {type(exc).__name__}: {exc}") from exc


@app.post("/embed/query")
def embed_query(req: QueryRequest) -> dict[str, Any]:
    try:
        dense = list(dense_model().query_embed(req.text))[0]
        sparse = list(sparse_model().query_embed(req.text))[0]
        return {
            "dense": [float(v) for v in dense.tolist()],
            "sparse": sparse_to_json(sparse),
            "model": DENSE_MODEL,
            "models": {
                "dense": DENSE_MODEL,
                "sparse": SPARSE_MODEL,
                "bm25_language": BM25_LANGUAGE,
            },
        }
    except Exception as exc:
        raise HTTPException(500, f"Query embedding failed: {type(exc).__name__}: {exc}") from exc


@app.post("/rerank")
def rerank(req: RerankRequest) -> dict[str, Any]:
    if not RERANKER_ENABLED:
        raise HTTPException(503, "Reranker is disabled")
    try:
        scores = list(reranker_model().rerank(req.query, req.documents))
        return {"scores": [float(x) for x in scores], "model": RERANKER_MODEL}
    except Exception as exc:
        raise HTTPException(500, f"Rerank failed: {type(exc).__name__}: {exc}") from exc
