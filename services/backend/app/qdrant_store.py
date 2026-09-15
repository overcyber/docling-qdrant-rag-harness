from __future__ import annotations

from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient, models

from .config import settings


@lru_cache(maxsize=1)
def client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=60,
    )


def _configured_dense_size(c: QdrantClient) -> int | None:
    """Return the configured size of the named dense vector, when discoverable."""
    info = c.get_collection(settings.qdrant_collection)
    vectors = info.config.params.vectors
    if isinstance(vectors, dict):
        dense_params = vectors.get("dense")
        size = getattr(dense_params, "size", None)
        return int(size) if size is not None else None
    return None


def _expected_embedding_identity(identity: dict[str, Any] | None = None) -> dict[str, str]:
    identity = identity or {}
    return {
        "dense": str(identity.get("dense") or settings.dense_model),
        "sparse": str(identity.get("sparse") or settings.sparse_model),
        "bm25_language": str(identity.get("bm25_language") or settings.bm25_language),
    }


def _assert_embedding_identity(c: QdrantClient, expected: dict[str, str]) -> None:
    points, _ = c.scroll(
        collection_name=settings.qdrant_collection,
        limit=1,
        with_payload=True,
        with_vectors=False,
    )
    if not points:
        return
    stored = (points[0].payload or {}).get("embedding_models") or {}
    if not isinstance(stored, dict) or not stored:
        # Collections created by older harness versions may not carry model identity.
        return
    mismatches = {
        key: {"collection": stored.get(key), "request": expected.get(key)}
        for key in ("dense", "sparse", "bm25_language")
        if stored.get(key) and expected.get(key) and stored.get(key) != expected.get(key)
    }
    if mismatches:
        raise RuntimeError(
            f"Qdrant embedding-space identity mismatch for collection "
            f"{settings.qdrant_collection!r}: {mismatches}. Use a new "
            "QDRANT_COLLECTION and reindex after changing embedding/sparse models."
        )


def ensure_collection(dense_size: int | None = None, embedding_identity: dict[str, Any] | None = None) -> None:
    c = client()
    expected_size = int(dense_size or settings.embedding_dim)
    expected_identity = _expected_embedding_identity(embedding_identity)

    if not c.collection_exists(settings.qdrant_collection):
        try:
            c.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config={
                    "dense": models.VectorParams(
                        size=expected_size,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    "sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)
                },
            )
        except Exception:
            # Multiple ingestion workers may race while creating the first collection.
            # Suppress only the benign case where another worker created it first.
            if not c.collection_exists(settings.qdrant_collection):
                raise

    actual_size = _configured_dense_size(c)
    if dense_size is not None and actual_size is not None and actual_size != expected_size:
        raise RuntimeError(
            f"Qdrant dense vector dimension mismatch for collection "
            f"{settings.qdrant_collection!r}: collection={actual_size}, "
            f"embedding_model={expected_size}. Reindex into a new QDRANT_COLLECTION "
            "after changing the dense embedding model."
        )
    _assert_embedding_identity(c, expected_identity)

    keyword_fields = ["tenant_id", "document_id", "sha256", "ingest_fingerprint", "filename", "chunker_type"]
    keyword_fields.extend(f"user_metadata.{x}" for x in settings.qdrant_metadata_index_fields)
    for field in keyword_fields:
        try:
            c.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )
        except Exception:
            # Creating an already-existing payload index is harmless.
            pass


def filter_for(
    tenant: str,
    document_id: str | None = None,
    sha256: str | None = None,
    filters: dict[str, Any] | None = None,
) -> models.Filter:
    must: list[models.FieldCondition] = [
        models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant))
    ]
    if document_id:
        must.append(models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id)))
    if sha256:
        must.append(models.FieldCondition(key="sha256", match=models.MatchValue(value=sha256)))

    for key, value in (filters or {}).items():
        if value is None:
            continue
        payload_key = (
            key
            if key in {"filename", "sha256", "document_id", "chunker_type", "ingest_fingerprint"}
            else f"user_metadata.{key}"
        )
        if isinstance(value, list):
            must.append(models.FieldCondition(key=payload_key, match=models.MatchAny(any=value)))
        else:
            must.append(models.FieldCondition(key=payload_key, match=models.MatchValue(value=value)))
    return models.Filter(must=must)


def delete_document(tenant: str, document_id: str) -> None:
    c = client()
    if not c.collection_exists(settings.qdrant_collection):
        return
    c.delete(
        collection_name=settings.qdrant_collection,
        points_selector=models.FilterSelector(filter=filter_for(tenant, document_id=document_id)),
        wait=True,
    )


def find_document_by_sha(tenant: str, sha256: str) -> dict[str, Any] | None:
    """Return one indexed chunk for a tenant/hash pair, if present."""
    c = client()
    if not c.collection_exists(settings.qdrant_collection):
        return None
    points, _ = c.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=filter_for(tenant, sha256=sha256),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )
    if not points:
        return None
    p = points[0]
    return {"id": str(p.id), "payload": p.payload or {}}



def find_document_by_fingerprint(tenant: str, ingest_fingerprint: str) -> dict[str, Any] | None:
    """Return one indexed chunk for an exact content+processing+metadata fingerprint."""
    c = client()
    if not c.collection_exists(settings.qdrant_collection):
        return None
    qfilter = models.Filter(
        must=[
            models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant)),
            models.FieldCondition(key="ingest_fingerprint", match=models.MatchValue(value=ingest_fingerprint)),
        ]
    )
    points, _ = c.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=qfilter,
        limit=1,
        with_payload=True,
        with_vectors=False,
    )
    if not points:
        return None
    point = points[0]
    return {"id": str(point.id), "payload": point.payload or {}}

def list_document_chunks(tenant: str, document_id: str, limit: int = 100) -> list[dict[str, Any]]:
    c = client()
    if not c.collection_exists(settings.qdrant_collection):
        return []
    points, _ = c.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=filter_for(tenant, document_id=document_id),
        limit=min(max(limit, 1), 1000),
        with_payload=True,
        with_vectors=False,
    )
    rows = [{"id": str(p.id), "payload": p.payload or {}} for p in points]
    rows.sort(key=lambda x: int(x["payload"].get("chunk_index", 0)))
    return rows


def search_points(
    *,
    tenant: str,
    dense: list[float],
    sparse: dict[str, list],
    mode: str,
    top_k: int,
    candidate_k: int,
    filters: dict[str, Any] | None = None,
    score_threshold: float | None = None,
    embedding_identity: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ensure_collection(dense_size=len(dense), embedding_identity=embedding_identity)
    c = client()
    qfilter = filter_for(tenant, filters=filters)
    sparse_vector = models.SparseVector(
        indices=[int(x) for x in sparse["indices"]],
        values=[float(x) for x in sparse["values"]],
    )

    if mode == "dense":
        response = c.query_points(
            collection_name=settings.qdrant_collection,
            query=dense,
            using="dense",
            query_filter=qfilter,
            limit=candidate_k,
            with_payload=True,
            with_vectors=False,
        )
    elif mode == "sparse":
        response = c.query_points(
            collection_name=settings.qdrant_collection,
            query=sparse_vector,
            using="sparse",
            query_filter=qfilter,
            limit=candidate_k,
            with_payload=True,
            with_vectors=False,
        )
    else:
        response = c.query_points(
            collection_name=settings.qdrant_collection,
            prefetch=[
                models.Prefetch(
                    query=sparse_vector,
                    using="sparse",
                    limit=candidate_k,
                    filter=qfilter,
                ),
                models.Prefetch(
                    query=dense,
                    using="dense",
                    limit=candidate_k,
                    filter=qfilter,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=candidate_k,
            with_payload=True,
            with_vectors=False,
        )

    out: list[dict[str, Any]] = []
    for p in response.points:
        score = float(p.score)
        if score_threshold is not None and score < score_threshold:
            continue
        out.append({"id": str(p.id), "score": score, "payload": p.payload or {}})
    return out[: max(top_k, candidate_k)]
