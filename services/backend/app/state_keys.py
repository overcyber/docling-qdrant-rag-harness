from __future__ import annotations


def job_owner_key(job_id: str) -> str:
    return f"ragjob-owner:{job_id}"


def ingest_reservation_key(tenant_id: str, ingest_fingerprint: str) -> str:
    return f"ragingest-reservation:{tenant_id}:{ingest_fingerprint}"
