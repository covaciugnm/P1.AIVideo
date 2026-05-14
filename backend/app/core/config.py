"""Application settings, loaded from .env via pydantic-settings.

`Settings` is intentionally instantiated as a module-level singleton so the
rest of the app can `from app.core.config import settings` cheaply.

DATABASE_URL is read at call time (not just at instantiation) so tests can
override it just by setting the env var before importing the engine.
"""
from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Runtime ---
    app_env: str = "development"
    log_level: str = "INFO"

    # --- Backend ---
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_cors_origins: str = "http://localhost:3000"

    # --- Postgres ---
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "aivideo"
    postgres_user: str = "aivideo"
    postgres_password: str = "changeme"

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # --- Queue topics ---
    queue_topic_compliance: str = "stage.compliance"
    queue_topic_orchestrator: str = "stage.orchestrator"
    queue_topic_audit: str = "audit.compliance"

    # --- Duration bounds ---
    target_duration_seconds: int = 30
    min_reel_duration_seconds: int = 15
    max_reel_duration_seconds: int = 60

    # --- Compliance posture ---
    require_synthetic_person_flag: bool = True
    allow_byo_likeness: bool = False
    banned_topics_path: str = "configs/policies/banned_topics.example.yaml"

    # --- Compliance token (Phase 2) ---
    compliance_signing_key: str = "phase2-noop-changeme"
    compliance_token_ttl_seconds: int = 3600
    allowed_lipsync_backend: str = "sadtalker"

    # --- Audio validation + artifacts (Phase 3D) ---
    audio_max_file_size_bytes: int = 52_428_800  # 50 MB
    audio_allowed_sample_rates: str = ""  # comma-separated; empty = any
    audio_allowed_channels: str = ""      # comma-separated; empty = any
    artifacts_local_root: str = "/storage/artifacts"

    # --- Provided face image (Phase 3E) ---
    image_max_file_size_bytes: int = 10_485_760  # 10 MB
    image_min_width: str = ""   # empty = no minimum
    image_min_height: str = ""

    # --- Upload intake (Phase 4A-2) ---
    # Where uploaded files land. Each subroot must be under a directory
    # that's also listed in PROVIDED_AUDIO_ALLOWED_ROOTS /
    # PROVIDED_IMAGE_ALLOWED_ROOTS so the existing path-safety validator
    # accepts the file when a job_from_inputs request later references it.
    uploads_local_root: str = "storage/inputs"
    upload_audio_root: str = "storage/inputs/audio"
    upload_image_root: str = "storage/inputs/images"
    upload_text_root: str = "storage/inputs/text"
    script_text_max_chars: int = 8000

    # --- Scriptwriter (Phase 3G) ---
    # Provider registry + contract config. NO real LLM calls happen until
    # both ``scriptwriter_enable_network_calls`` is True AND a real
    # provider has been activated. Default backend is "template".
    scriptwriter_backend: str = "template"
    scriptwriter_model: str = "qwen3.6"
    scriptwriter_fallback_model: str = "qwen3:8b"
    scriptwriter_allowed_backends: str = (
        "template,mock,ollama,vllm,openai_compatible,openai,anthropic,local_http"
    )
    scriptwriter_enable_network_calls: bool = False
    scriptwriter_timeout_seconds: int = 60
    scriptwriter_max_output_tokens: int = 800
    scriptwriter_temperature: float = 0.7
    scriptwriter_prompt_version: str = "v1"
    llm_provider_config_path: str = "configs/llm/providers.example.yaml"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    def get_database_url(self) -> str:
        """Resolve at call time so tests can set DATABASE_URL after import."""
        override = os.environ.get("DATABASE_URL")
        if override:
            return override
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def get_redis_url(self) -> str:
        override = os.environ.get("REDIS_URL")
        if override:
            return override
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()
