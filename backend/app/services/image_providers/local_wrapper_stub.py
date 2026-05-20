"""Local GPU-wrapper image providers — Phase 12W.

Concrete adapters that talk to the sibling Docker wrappers
(``docker/model-flux``, ``docker/model-sdxl``, ``docker/model-sd35``)
or to operator-managed upstream services (ComfyUI ``/prompt``,
AUTOMATIC1111 ``/sdapi/v1/txt2img``).

When the wrapper URL is configured AND reachable, the adapter posts a
real generate request and returns the produced PNG. When the URL is
unset, the adapter raises :class:`ProviderUnavailableError` with a
categorised error code that the router translates 1:1 to the public
:class:`CharacterImageGenerateError`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

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


class LocalWrapperImageProviderStub(ImageProvider):
    """Adapter that proxies the operator's generate request to a sibling
    GPU wrapper container over HTTP.

    Sub-flavours configured via :meth:`build`:
    - ``flux``: posts to ``${FLUX_LOCAL_BASE_URL}/flux/generate``.
    - ``sd35``: posts to ``${SD35_LOCAL_BASE_URL}/sd35/generate``.
    - ``sdxl``: posts to ``${SDXL_LOCAL_BASE_URL}/sdxl/generate``.
    - ``comfyui``: posts a workflow JSON to ``${COMFYUI_BASE_URL}/prompt``.
    - ``a1111``: posts to ``${A1111_BASE_URL}/sdapi/v1/txt2img``.
    """

    base_url_env: str = ""
    models_root_env: str = ""
    runtime_label: str = ""
    # Native API style: "diffusers" (our wrappers), "comfyui", "a1111".
    api_style: str = "diffusers"
    # Path component appended to the base URL for generate calls.
    generate_path: str = ""
    capabilities = ProviderCapabilities(
        text_to_image=True,
        image_to_image=True,
        reference_image=True,
        multi_reference=False,
        negative_prompt=True,
        seed=True,
        local=True,
        api=False,
    )

    @classmethod
    def build(
        cls,
        *,
        provider_id: str,
        display_name: str,
        default_model: str | None,
        base_url_env: str,
        models_root_env: str = "",
        runtime_label: str = "",
    ) -> "LocalWrapperImageProviderStub":
        instance = cls()
        instance.provider_id = provider_id
        instance.display_name = display_name
        instance.default_model = default_model
        instance.base_url_env = base_url_env
        instance.models_root_env = models_root_env
        instance.runtime_label = runtime_label or display_name
        # API style derived from provider_id.
        if provider_id == "flux_local":
            instance.api_style = "diffusers"
            instance.generate_path = "/flux/generate"
        elif provider_id == "sd35_local":
            instance.api_style = "diffusers"
            instance.generate_path = "/sd35/generate"
        elif provider_id == "sdxl_local":
            instance.api_style = "diffusers"
            instance.generate_path = "/sdxl/generate"
        elif provider_id == "comfyui_local":
            instance.api_style = "comfyui"
            instance.generate_path = "/prompt"
        elif provider_id == "a1111_local":
            instance.api_style = "a1111"
            instance.generate_path = "/sdapi/v1/txt2img"
        return instance

    def _resolve_base_url(self) -> str | None:
        value = os.environ.get(self.base_url_env, "").strip()
        return value or None

    async def health_check(self) -> ProviderHealth:
        base = self._resolve_base_url()
        if not base:
            return ProviderHealth(
                status="not_configured",
                notes=(
                    f"{self.runtime_label} wrapper not configured. "
                    f"Set {self.base_url_env} and start the wrapper container."
                ),
            )
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(base.rstrip("/") + "/health")
            if r.status_code // 100 != 2:
                return ProviderHealth(
                    status="error",
                    notes=f"Wrapper at {base} responded HTTP {r.status_code}.",
                )
            return ProviderHealth(
                status="available",
                notes=f"{self.runtime_label} wrapper reachable.",
            )
        except Exception as exc:  # pragma: no cover — defensive
            return ProviderHealth(
                status="error",
                notes=f"Probe failed: {type(exc).__name__}: {exc}",
            )

    async def generate_text_to_image(
        self, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        base = self._resolve_base_url()
        if not base:
            raise ProviderUnavailableError(
                "provider_not_configured",
                (
                    f"{self.runtime_label} wrapper not configured. "
                    f"Set {self.base_url_env} and start the Docker wrapper "
                    "(mirrors the model-sadtalker pattern)."
                ),
                fallback="mock",
            )
        if self.api_style == "diffusers":
            return await self._call_diffusers_wrapper(base, request)
        if self.api_style == "comfyui":
            return await self._call_comfyui(base, request)
        if self.api_style == "a1111":
            return await self._call_a1111(base, request)
        raise ProviderUnavailableError(
            "provider_not_implemented",
            f"Unknown api_style {self.api_style!r}.",
        )

    async def generate_image_to_image(
        self, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        # ComfyUI/A1111 can do img2img with a different endpoint; for
        # our diffusers wrappers img2img isn't wired yet (Phase 12W+1).
        # For now, fall back to text-to-image — the prompt still
        # references the persona via the script context block.
        return await self.generate_text_to_image(request)

    # ------------------------------------------------------------------
    # Backend-specific HTTP calls
    # ------------------------------------------------------------------

    async def _call_diffusers_wrapper(
        self, base: str, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        payload: dict[str, Any] = {
            "prompt": request.prompt or "",
            "width": request.width,
            "height": request.height,
        }
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt
        if request.seed is not None:
            payload["seed"] = int(request.seed)
        if request.steps is not None:
            payload["steps"] = int(request.steps)
        if request.guidance_scale is not None:
            payload["guidance_scale"] = float(request.guidance_scale)
        if request.model_id:
            payload["model_id"] = request.model_id
        if request.reference_image_path:
            payload["reference_image_path"] = request.reference_image_path

        url = base.rstrip("/") + self.generate_path
        # Generation can take 30s–5min depending on model + steps. Cap at
        # 10 min — operator can override via env if they need longer.
        timeout_s = float(os.environ.get("IMAGE_GENERATOR_TIMEOUT_SECONDS", "600"))
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.post(url, json=payload)
        except Exception as exc:
            logger.warning("%s generate HTTP call failed: %s", self.runtime_label, exc)
            raise ProviderUnavailableError(
                "generation_failed",
                f"HTTP call to wrapper failed: {type(exc).__name__}: {exc}",
                fallback="mock",
            ) from exc

        if response.status_code // 100 != 2:
            try:
                detail = response.json()
            except Exception:
                detail = {"error_code": "generation_failed", "detail": response.text[:500]}
            code = detail.get("error_code", "generation_failed")
            msg = detail.get("detail", "wrapper returned an error")
            raise ProviderUnavailableError(code, msg, fallback="mock")

        body = response.json()
        file_path = body.get("file_path")
        if not file_path:
            raise ProviderUnavailableError(
                "generation_failed",
                f"Wrapper returned no file_path. Body: {body!r}",
            )
        # The wrapper writes to a shared volume; read it back into bytes
        # so the character image service can compute a checksum and
        # store it under the per-character directory.
        try:
            data = Path(file_path).read_bytes()
        except OSError as exc:
            raise ProviderUnavailableError(
                "storage_failed",
                f"Wrapper-produced file {file_path} not readable: {exc}",
            ) from exc

        return ImageGenerationResult(
            image_bytes=data,
            mime_type=body.get("mime_type", "image/png"),
            width=int(body.get("width", request.width)),
            height=int(body.get("height", request.height)),
            seed=body.get("seed"),
            model_id=body.get("model_id") or request.model_id or self.default_model,
            provider_metadata={
                "provider_id": self.provider_id,
                "wrapper_url": base,
                "duration_seconds": body.get("duration_seconds"),
                "wrapper_size_bytes": body.get("size_bytes"),
                "wrapper_file_path": file_path,
            },
        )

    def _resolve_workflow_template(self, request: ImageGenerationInput) -> str:
        """Phase IG-1 — locate the ComfyUI workflow template.

        Priority:
          1. ``request.workflow_name`` → ``${COMFYUI_WORKFLOW_DIR}/<name>.json``
             (identity-consistent workflows like ``pulid_flux_consistent``).
          2. legacy single ``COMFYUI_WORKFLOW_PATH`` env (back-compat).
        Returns the raw template text (placeholders not yet substituted).
        """
        name = (request.workflow_name or "").strip()
        if name:
            wf_dir = os.environ.get("COMFYUI_WORKFLOW_DIR", "/workflows").strip()
            # Defensive: only a bare file stem, never a path traversal.
            safe = name.replace("..", "").strip("/")
            candidate = Path(wf_dir) / f"{safe}.json"
            try:
                return candidate.read_text(encoding="utf-8")
            except OSError as exc:
                raise ProviderUnavailableError(
                    "provider_not_configured",
                    f"ComfyUI workflow {name!r} not found at {candidate} "
                    f"(set COMFYUI_WORKFLOW_DIR; see workflows/comfyui/README.md): {exc}",
                ) from exc
        wf_path = os.environ.get("COMFYUI_WORKFLOW_PATH", "").strip()
        if not wf_path:
            raise ProviderUnavailableError(
                "provider_not_configured",
                "No ComfyUI workflow selected. Pass workflow_name (resolved "
                "under COMFYUI_WORKFLOW_DIR) or set COMFYUI_WORKFLOW_PATH.",
            )
        try:
            return Path(wf_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise ProviderUnavailableError(
                "provider_not_configured",
                f"ComfyUI workflow template at {wf_path} not readable: {exc}",
            ) from exc

    @staticmethod
    def _build_workflow_dict(
        template: str,
        request: ImageGenerationInput,
        seed_val: int,
        face_ref_name: str,
        body_ref_name: str,
    ) -> dict:
        """Phase IG-1 — substitute placeholders into a ComfyUI template and
        parse the result. Pure + side-effect-free so it is unit-testable
        without a live ComfyUI server. Raises ProviderUnavailableError if
        the substituted text is not valid JSON."""
        import json

        def _esc(s: str) -> str:
            # JSON-escape a value for safe substitution inside a JSON string.
            return json.dumps(s)[1:-1]

        workflow_json = (
            template.replace("__PROMPT__", _esc(request.prompt or ""))
            .replace("__NEGATIVE__", _esc(request.negative_prompt or ""))
            .replace("__SEED__", str(seed_val))
            .replace("__WIDTH__", str(request.width))
            .replace("__HEIGHT__", str(request.height))
            .replace("__STEPS__", str(int(request.steps) if request.steps else 28))
            .replace(
                "__CFG__",
                str(float(request.guidance_scale) if request.guidance_scale else 3.5),
            )
            .replace("__FACE_REF__", _esc(face_ref_name))
            .replace("__BODY_REF__", _esc(body_ref_name))
        )
        try:
            parsed = json.loads(workflow_json)
        except json.JSONDecodeError as exc:
            raise ProviderUnavailableError(
                "provider_not_configured",
                f"ComfyUI workflow JSON invalid after substitution: {exc}",
            ) from exc
        # ComfyUI treats every top-level key as a node id. Drop our doc-only
        # keys (e.g. ``_comment``) so they aren't validated as nodes.
        return {k: v for k, v in parsed.items() if not str(k).startswith("_")}

    async def _comfyui_upload_image(
        self, client: "httpx.AsyncClient", base: str, local_path: str
    ) -> str:
        """Phase IG-1 — push a reference image into ComfyUI's input dir via
        ``/upload/image`` and return the server-side filename to inject into
        a LoadImage node. Raises ProviderUnavailableError on failure."""
        try:
            data = Path(local_path).read_bytes()
        except OSError as exc:
            raise ProviderUnavailableError(
                "reference_image_missing",
                f"Reference image {local_path} not readable: {exc}",
            ) from exc
        files = {"image": (Path(local_path).name, data, "image/png")}
        resp = await client.post(
            base.rstrip("/") + "/upload/image",
            files=files,
            data={"overwrite": "true"},
        )
        if resp.status_code // 100 != 2:
            raise ProviderUnavailableError(
                "generation_failed",
                f"ComfyUI /upload/image returned {resp.status_code}: {resp.text[:200]}",
            )
        body = resp.json()
        name = body.get("name")
        subfolder = body.get("subfolder", "")
        if not name:
            raise ProviderUnavailableError(
                "generation_failed", f"ComfyUI upload returned no name: {body!r}"
            )
        return f"{subfolder}/{name}" if subfolder else name

    async def _call_comfyui(
        self, base: str, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        # ComfyUI workflows are JSON DAGs. We substitute the prompt + seed +
        # dimensions + (for identity-consistent workflows) the uploaded
        # face / full-body reference filenames into named placeholders.
        import json
        import time
        import uuid as _uuid

        template = self._resolve_workflow_template(request)
        seed_val = int(request.seed) if request.seed is not None else int(time.time())

        client_id = _uuid.uuid4().hex
        timeout_s = float(os.environ.get("IMAGE_GENERATOR_TIMEOUT_SECONDS", "600"))
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            # Identity references must be uploaded BEFORE substitution so we
            # can inject the server-side filenames into the LoadImage nodes.
            face_ref_name = ""
            body_ref_name = ""
            if request.face_reference_path:
                face_ref_name = await self._comfyui_upload_image(
                    client, base, request.face_reference_path
                )
            if request.body_reference_path:
                body_ref_name = await self._comfyui_upload_image(
                    client, base, request.body_reference_path
                )

            workflow = self._build_workflow_dict(
                template, request, seed_val, face_ref_name, body_ref_name
            )

            queue_resp = await client.post(
                base.rstrip("/") + "/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )
            if queue_resp.status_code // 100 != 2:
                raise ProviderUnavailableError(
                    "generation_failed",
                    f"ComfyUI queued returned {queue_resp.status_code}: {queue_resp.text[:300]}",
                )
            prompt_id = queue_resp.json().get("prompt_id")
            if not prompt_id:
                raise ProviderUnavailableError(
                    "generation_failed",
                    f"ComfyUI returned no prompt_id: {queue_resp.json()!r}",
                )
            # Poll history endpoint until the prompt completes.
            import asyncio

            deadline = time.time() + timeout_s
            history: dict | None = None
            while time.time() < deadline:
                await asyncio.sleep(2.0)
                r = await client.get(base.rstrip("/") + f"/history/{prompt_id}")
                if r.status_code == 200:
                    body = r.json() or {}
                    if prompt_id in body:
                        history = body[prompt_id]
                        break
            if history is None:
                raise ProviderUnavailableError(
                    "generation_failed", "ComfyUI poll timeout"
                )
            outputs = history.get("outputs") or {}
            image_filename = None
            image_subfolder = ""
            for _node_id, node_out in outputs.items():
                imgs = node_out.get("images") or []
                if imgs:
                    image_filename = imgs[0].get("filename")
                    image_subfolder = imgs[0].get("subfolder", "")
                    break
            if not image_filename:
                raise ProviderUnavailableError(
                    "generation_failed",
                    f"ComfyUI produced no image output. Outputs: {outputs!r}",
                )
            view_resp = await client.get(
                base.rstrip("/") + "/view",
                params={
                    "filename": image_filename,
                    "subfolder": image_subfolder,
                    "type": "output",
                },
            )
            if view_resp.status_code // 100 != 2:
                raise ProviderUnavailableError(
                    "generation_failed",
                    f"ComfyUI /view returned {view_resp.status_code}",
                )
            data = view_resp.content

        return ImageGenerationResult(
            image_bytes=data,
            mime_type="image/png",
            width=request.width,
            height=request.height,
            seed=seed_val,
            model_id=request.model_id or self.default_model,
            provider_metadata={
                "provider_id": self.provider_id,
                "wrapper_url": base,
                "comfyui_prompt_id": prompt_id,
                "comfyui_filename": image_filename,
                "workflow_name": request.workflow_name,
                "face_reference_used": bool(request.face_reference_path),
                "body_reference_used": bool(request.body_reference_path),
            },
        )

    async def _call_a1111(
        self, base: str, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        import base64 as _b64

        payload: dict[str, Any] = {
            "prompt": request.prompt or "",
            "width": request.width,
            "height": request.height,
            "steps": int(request.steps) if request.steps else 30,
            "cfg_scale": float(request.guidance_scale) if request.guidance_scale else 7.0,
        }
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt
        if request.seed is not None:
            payload["seed"] = int(request.seed)
        if request.model_id:
            # A1111 expects model swap via /sdapi/v1/options upfront — we
            # keep the operator's selected model on the upstream side and
            # only forward the prompt here.
            payload["override_settings"] = {"sd_model_checkpoint": request.model_id}

        timeout_s = float(os.environ.get("IMAGE_GENERATOR_TIMEOUT_SECONDS", "600"))
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(
                base.rstrip("/") + "/sdapi/v1/txt2img",
                json=payload,
            )
        if r.status_code // 100 != 2:
            raise ProviderUnavailableError(
                "generation_failed",
                f"A1111 returned HTTP {r.status_code}: {r.text[:300]}",
            )
        body = r.json()
        images_b64 = body.get("images") or []
        if not images_b64:
            raise ProviderUnavailableError(
                "generation_failed", "A1111 returned no images."
            )
        data = _b64.b64decode(images_b64[0])
        return ImageGenerationResult(
            image_bytes=data,
            mime_type="image/png",
            width=request.width,
            height=request.height,
            seed=request.seed,
            model_id=request.model_id or self.default_model,
            provider_metadata={
                "provider_id": self.provider_id,
                "wrapper_url": base,
                "a1111_info": body.get("info"),
            },
        )


# Per-provider configuration. ``ImageProvider.build()`` returns one
# wired instance; the dispatch module instantiates these on demand.
LOCAL_WRAPPER_DEFINITIONS: tuple[dict, ...] = (
    {
        "provider_id": "flux_local",
        "display_name": "FLUX.1 local (open-weights, GPU wrapper)",
        "default_model": "flux.1-schnell",
        "base_url_env": "FLUX_LOCAL_BASE_URL",
        "models_root_env": "FLUX_LOCAL_MODELS_ROOT",
        "runtime_label": "FLUX.1 local",
    },
    {
        "provider_id": "sd35_local",
        "display_name": "Stable Diffusion 3.5 Large (local, GPU wrapper)",
        "default_model": "stable-diffusion-3.5-large",
        "base_url_env": "SD35_LOCAL_BASE_URL",
        "models_root_env": "SD35_LOCAL_MODELS_ROOT",
        "runtime_label": "Stable Diffusion 3.5",
    },
    {
        "provider_id": "sdxl_local",
        "display_name": "Stable Diffusion XL (local, GPU wrapper)",
        "default_model": "sdxl-base-1.0",
        "base_url_env": "SDXL_LOCAL_BASE_URL",
        "models_root_env": "SDXL_LOCAL_MODELS_ROOT",
        "runtime_label": "SDXL local",
    },
    {
        "provider_id": "comfyui_local",
        "display_name": "ComfyUI workflow runner (local)",
        "default_model": None,
        "base_url_env": "COMFYUI_BASE_URL",
        "models_root_env": "COMFYUI_MODELS_ROOT",
        "runtime_label": "ComfyUI",
    },
    {
        "provider_id": "a1111_local",
        "display_name": "AUTOMATIC1111 WebUI (local)",
        "default_model": None,
        "base_url_env": "A1111_BASE_URL",
        "models_root_env": "A1111_MODELS_ROOT",
        "runtime_label": "AUTOMATIC1111 WebUI",
    },
)
