"""User settings router — API key storage (BYOK)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ApiKeyRequest(BaseModel):
    api_key: str


def _get_user(request: Request) -> str:
    return request.headers.get("x-user-email", "default")


def _mask_key(key: str) -> str:
    """Show first 10 and last 4 chars, fixed-width mask."""
    if len(key) <= 14:
        return key[:4] + "••••" + key[-4:]
    return key[:10] + "••••••••" + key[-4:]


@router.get("")
async def get_settings(request: Request):
    """Get user settings (masked API key)."""
    db = request.app.state.db
    # For now, single-user mode — use a fixed user ID
    # Will be replaced with JWT user ID when backend auth is added
    doc = await db.user_settings.find_one({"user_id": _get_user(request)})
    if not doc:
        return {"has_api_key": False, "masked_key": None}
    
    api_key = doc.get("api_key", "")
    return {
        "has_api_key": bool(api_key),
        "masked_key": _mask_key(api_key) if api_key else None,
    }


@router.post("/api-key")
async def save_api_key(request: Request, body: ApiKeyRequest):
    """Save or update Anthropic API key."""
    db = request.app.state.db
    key = body.api_key.strip()
    
    if not key.startswith("sk-ant-"):
        return {"error": "Invalid API key format. Must start with sk-ant-"}, 400
    
    await db.user_settings.update_one(
        {"user_id": _get_user(request)},
        {
            "$set": {
                "api_key": key,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "$setOnInsert": {
                "user_id": _get_user(request),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        },
        upsert=True,
    )
    
    logger.info("API key saved for user: default")
    return {"success": True, "masked_key": _mask_key(key)}


@router.delete("/api-key")
async def delete_api_key(request: Request):
    """Delete stored API key."""
    db = request.app.state.db
    await db.user_settings.update_one(
        {"user_id": _get_user(request)},
        {"$set": {"api_key": "", "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    logger.info("API key deleted for user: default")
    return {"success": True}
