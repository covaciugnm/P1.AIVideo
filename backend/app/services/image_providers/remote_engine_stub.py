"""Remote engine image provider — connect to an external generation
orchestrator over the LAN (e.g. the GB10 / ThinkStation box).

Unlike the sibling ``local_wrapper_stub`` adapters — which share the
``/storage/artifacts`` Docker volume and therefore read the result back by
``file_path`` — a remote engine runs on a *different machine*, so it returns
the image **inline** (base64 PNG). This adapter base64-decodes the response
into ``image_bytes`` directly; there is no shared filesystem assumption.

Wiring (3 knobs, no code change to swap the engine):
  - ``REMOTE_IMAGE_BASE_URL``   e.g. ``http://192.168.100.151:8080`` (DHCP — do
                                NOT hardcode; the engine exposes ``/whoami``).
  - ``REMOTE_ENGINE_API_KEY``   sent as ``Authorization: Bearer <key>``. Keep
                                it in the Keys vault (loaded into os.environ at
                                startup) or in ``.env``.
  - ``REMOTE_IMAGE_TIMEOUT_SECONDS`` (optional, default 600).

Contract (text→image):
  POST {base}/engine/generate
    {"prompt": str, "width": int, "height": int, "seed": int|None,
     "engine": str, "steps": int|None, "return": "base64"}
  → 200 {"engine":..., "effective_model":..., "fallback_used":bool,
         "seed":int, "image_base64":"<PNG>"}
  → 4xx/5xx {"error_code":"...","detail":"..."}
"""
from __future__ import annotations

import base64
import logging
import os

import httpx

from app.services.image_providers.base import (
    ImageGenerationInput,
    ImageGenerationResult,
    ImageProvider,
    ProviderCapabilities,
    ProviderHealth,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)

PROVIDER_ID = "remote_gb10_image"
BASE_URL_ENV = "REMOTE_IMAGE_BASE_URL"
API_KEY_ENV = "REMOTE_ENGINE_API_KEY"
# Default engine the remote orchestrator exposes (fast preview). The UI's
# model_id, when set, overrides this so the operator can pick a heavier engine.
DEFAULT_ENGINE = "image-preview-fast"


class RemoteEngineImageProvider(ImageProvider):
    """Calls a remote HTTP generation orchestrator (Bearer-authenticated)."""

    provider_id = PROVIDER_ID
    display_name = "GB10 (ThinkStation) — remote engine"
    default_model = DEFAULT_ENGINE
    capabilities = ProviderCapabilities(
        text_to_image=True,
        image_to_image=False,
        reference_image=False,
        negative_prompt=False,
        seed=True,
        local=False,
        api=True,
    )

    def _base_url(self) -> str | None:
        v = os.environ.get(BASE_URL_ENV, "").strip()
        return v.rstrip("/") or None

    def _api_key(self) -> str:
        return os.environ.get(API_KEY_ENV, "").strip()

    def _headers(self) -> dict[str, str]:
        key = self._api_key()
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    async def health_check(self) -> ProviderHealth:
        base = self._base_url()
        if not base:
            return ProviderHealth(
                status="not_configured",
                notes=f"Set {BASE_URL_ENV} (+ {API_KEY_ENV}) to enable the remote engine.",
            )
        if not self._api_key():
            return ProviderHealth(
                status="not_configured",
                notes=f"{API_KEY_ENV} is empty — the remote engine requires a Bearer key.",
            )
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(f"{base}/whoami")
            if r.status_code // 100 != 2:
                return ProviderHealth(
                    status="error", notes=f"{base}/whoami responded HTTP {r.status_code}."
                )
            host = (r.json() or {}).get("host_ip", "?")
            return ProviderHealth(status="available", notes=f"Remote engine reachable (host {host}).")
        except Exception as exc:  # pragma: no cover — defensive
            return ProviderHealth(status="error", notes=f"Probe failed: {type(exc).__name__}: {exc}")

    async def generate_text_to_image(
        self, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        base = self._base_url()
        if not base:
            raise ProviderUnavailableError(
                "provider_not_configured",
                f"Remote engine not configured. Set {BASE_URL_ENV} and {API_KEY_ENV}.",
                fallback="mock",
            )
        if not self._api_key():
            raise ProviderUnavailableError(
                "provider_not_configured",
                f"{API_KEY_ENV} is empty — the remote engine requires a Bearer key.",
                fallback="mock",
            )

        # The UI's model_id selects the remote "engine"; fall back to the fast
        # preview engine when the operator didn't pick one.
        engine = (request.model_id or DEFAULT_ENGINE).strip()
        body: dict = {
            "prompt": request.prompt or "",
            "width": request.width,
            "height": request.height,
            "seed": request.seed,
            "engine": engine,
            "return": "base64",
        }
        if request.steps is not None:
            body["steps"] = int(request.steps)

        timeout_s = float(os.environ.get("REMOTE_IMAGE_TIMEOUT_SECONDS", "600"))
        url = f"{base}/engine/generate"
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.post(url, json=body, headers=self._headers())
        except Exception as exc:
            logger.warning("remote_engine generate HTTP call failed: %s", exc)
            raise ProviderUnavailableError(
                "generation_failed",
                f"HTTP call to remote engine failed: {type(exc).__name__}: {exc}",
                fallback="mock",
            ) from exc

        if response.status_code == 401:
            raise ProviderUnavailableError(
                "provider_not_configured",
                "Remote engine rejected the API key (HTTP 401). Check REMOTE_ENGINE_API_KEY.",
                fallback="mock",
            )
        if response.status_code // 100 != 2:
            try:
                detail = response.json()
            except Exception:
                detail = {"error_code": "generation_failed", "detail": response.text[:500]}
            raise ProviderUnavailableError(
                detail.get("error_code", "generation_failed"),
                detail.get("detail", "remote engine returned an error"),
                fallback="mock",
            )

        body_json = response.json()
        b64 = body_json.get("image_base64")
        if not b64:
            raise ProviderUnavailableError(
                "generation_failed",
                f"Remote engine returned no image_base64. Body keys: {sorted(body_json)!r}",
            )
        try:
            image_bytes = base64.b64decode(b64)
        except Exception as exc:
            raise ProviderUnavailableError(
                "generation_failed", f"Could not decode image_base64: {exc}"
            ) from exc

        return ImageGenerationResult(
            image_bytes=image_bytes,
            mime_type="image/png",
            width=request.width,
            height=request.height,
            seed=body_json.get("seed", request.seed),
            model_id=body_json.get("effective_model") or engine,
            provider_metadata={
                "engine": body_json.get("engine", engine),
                "effective_model": body_json.get("effective_model"),
                "fallback_used": body_json.get("fallback_used"),
                "remote": True,
            },
        )
