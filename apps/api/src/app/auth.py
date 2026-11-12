"""API-key authentication for the write route."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from app.config import get_settings


def require_integrator(x_api_key: str | None = Header(default=None)) -> str:
    """Return the integrator name for a valid ``X-API-Key``, else answer 401."""
    keys = get_settings().api_key_map()
    if not keys:
        raise HTTPException(status_code=503, detail="no API keys are configured on this attester")
    if x_api_key:
        for key, name in keys.items():
            if hmac.compare_digest(key.encode(), x_api_key.encode()):
                return name
    raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")
