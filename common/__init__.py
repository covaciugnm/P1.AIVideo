"""Shared enums + Pydantic schemas used by both `backend/app` and `agents/`.

Layering rule: `common` may not import from `app` or `agents`. Both backend
and agents may import from `common`.
"""
