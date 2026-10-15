"""API keys: list, make and revoke the credentials agents and scripts use.

Admin only (policy.py); making one also wants the password confirmed, since a
key outlives the session making it. The secret is in the response that makes
the key and nowhere else, ever.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from boneio.core.auth.api_keys import DEFAULT_LIFETIME_DAYS, ApiKeyError, ApiKeyStore, KeyScope
from boneio.webui import security_events
from boneio.webui.middleware.auth import get_key_store

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api-keys"])


class NewKey(BaseModel):
    name: str
    scope: KeyScope
    days: int = DEFAULT_LIFETIME_DAYS


def _store() -> ApiKeyStore:
    store = get_key_store()
    if store is None:
        raise HTTPException(status_code=503, detail="API keys are not available on this device.")
    return store


@router.get("/api-keys")
async def list_api_keys():
    """Every key, without its secret."""
    keys = await asyncio.to_thread(_store().list_keys)
    return {"keys": [key.public() for key in keys]}


@router.post("/api-keys")
async def create_api_key(body: NewKey, request: Request):
    """Make a key for the caller. The secret is shown this once."""
    owner = getattr(request.state, "user", None) or ""
    try:
        key, secret = await asyncio.to_thread(_store().create, body.name, owner, body.scope, body.days)
    except ApiKeyError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    security_events.emit(
        "api_key_created",
        username=owner,
        client=request.client.host if request.client else None,
        where=f"'{key.name}', {key.scope}, until {key.expires_at[:10]}",
    )
    return {"key": key.public(), "secret": secret}


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str):
    """Revoke a key; it stops working at once."""
    try:
        key = await asyncio.to_thread(_store().revoke, key_id)
    except ApiKeyError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return {"revoked": key.public()}
