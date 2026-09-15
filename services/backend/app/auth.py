from __future__ import annotations

import re

from fastapi import Header, HTTPException, Request

from .config import settings

_TENANT_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,128}$")


def require_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Require either Bearer auth or X-API-Key when API_KEY is configured."""
    if not settings.api_key:
        return
    if authorization == f"Bearer {settings.api_key}" or x_api_key == settings.api_key:
        return
    raise HTTPException(status_code=401, detail="Invalid or missing API credential")


def tenant_id(request: Request) -> str:
    value = (request.headers.get(settings.tenant_header_name) or settings.default_tenant_id).strip()
    if not _TENANT_RE.fullmatch(value):
        raise HTTPException(400, f"Invalid {settings.tenant_header_name}")
    return value
