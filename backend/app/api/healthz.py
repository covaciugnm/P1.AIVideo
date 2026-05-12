"""Health endpoint."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "phase": "1", "scope": "metadata-only"}
