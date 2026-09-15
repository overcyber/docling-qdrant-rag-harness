from __future__ import annotations

import asyncio
import json
from typing import Any

from .config import settings


async def _publish(subject: str, payload: dict[str, Any]) -> None:
    import nats

    nc = await nats.connect(settings.nats_url, connect_timeout=2, max_reconnect_attempts=1)
    try:
        full_subject = f"{settings.nats_subject_prefix}.{subject}".strip(".")
        await nc.publish(full_subject, json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
        await nc.flush(timeout=2)
    finally:
        await nc.close()


def publish_event(subject: str, payload: dict[str, Any]) -> None:
    if not settings.nats_enabled:
        return
    try:
        asyncio.run(_publish(subject, payload))
    except Exception:
        # Event delivery is deliberately non-fatal; Celery remains the authoritative work queue.
        return
