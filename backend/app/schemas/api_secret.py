"""API secrets schemas — Phase 12X."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SecretCategory = Literal[
    "huggingface",
    "image_generator",
    "llm",
    "tts",
    "local_endpoint",
    "misc",
]


class ApiSecretCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_name: str = Field(..., min_length=1, max_length=160)
    value: str = Field(..., min_length=0, max_length=20000)
    description: str | None = Field(default=None, max_length=500)
    category: SecretCategory = "misc"


class ApiSecretUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(..., min_length=0, max_length=20000)


class ApiSecretResponse(BaseModel):
    """Operator-visible row. Per user request the value is NOT masked —
    the keys page is for an authenticated operator on their own machine.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    key_name: str
    value: str
    description: str | None
    category: SecretCategory
    last_tested_at: datetime | None
    last_test_status: str | None
    last_test_detail: str | None
    created_at: datetime
    updated_at: datetime


class ApiSecretListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ApiSecretResponse]
    catalog: list["ApiSecretCatalogEntry"]


class ApiSecretCatalogEntry(BaseModel):
    """One row of the predeclared key catalog rendered on the UI.

    The catalog is the canonical list of credentials the app cares
    about. The operator can also save arbitrary extra keys — they
    appear at the bottom of the page.
    """

    model_config = ConfigDict(extra="forbid")

    key_name: str
    description: str
    category: SecretCategory
    test_probe: str  # short human-readable description of what /test does


class ApiSecretTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_name: str
    status: Literal["ok", "failed", "skipped"]
    detail: str
    last_tested_at: datetime
