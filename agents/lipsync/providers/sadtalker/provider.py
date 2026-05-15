"""SadTalker provider — Phase 3A stub + Phase 7B hardening.

Implements ``LipSyncProvider`` for the agents/orchestrator path and adds
the Phase 7B inspection helpers consumed by the backend's
``/api/v1/video/generate`` readiness gate:

- ``inspect_runtime()`` — is torch importable?
- ``inspect_assets()`` — are weights on disk under ``SADTALKER_MODELS_ROOT``?
- ``inspect_gpu()``     — is a CUDA device visible at this moment?
- ``inspect_status()``  — combined readiness summary the catalog reads.
- ``generate()``        — refuses real inference unless every Phase 7B
                          gate (``RUN_REAL_SADTALKER=1``,
                          ``SADTALKER_ENABLE_REAL_INFERENCE=true``,
                          torch importable, CUDA visible, weights on
                          disk) is satisfied. Phase 7B itself never lets
                          the real path actually fire — the gates exist
                          so 7D / 7E can flip them on cleanly.

This module imports **nothing** from torch / diffusers / transformers /
opencv / SadTalker at module load. All heavy imports are lazy and live
inside the methods that explicitly need them.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path
from typing import ClassVar, Literal

from common.exceptions import (
    ComplianceTokenError,
    MissingAssetsError,
    ProviderNotImplementedError,
)
from common.schemas import (
    AssetSpec,
    ComplianceTokenClaims,
    ProviderHealth,
)
from common.enums import ProviderHealthStatus

from agents.compliance_officer.compliance_token import verify_token
from agents.lipsync.core.provider import (
    LipSyncProvider,
    LipSyncRequest,
    LipSyncResult,
)


# Phase 7B inspection status vocabulary. These map 1:1 to the
# ``video_*`` codes the backend surfaces from /api/v1/video/generate.
SadTalkerStatus = Literal[
    "not_configured",
    "runtime_missing",
    "assets_missing",
    "gpu_unavailable",
    "ready",
    "not_implemented",
]


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_models_root() -> Path | None:
    """SADTALKER_MODELS_ROOT wins; otherwise LIPSYNC_MODELS_ROOT/sadtalker."""
    explicit = os.environ.get("SADTALKER_MODELS_ROOT")
    if explicit:
        return Path(explicit)
    lipsync_root = os.environ.get("LIPSYNC_MODELS_ROOT")
    if lipsync_root:
        return Path(lipsync_root) / "sadtalker"
    return None


def _resolve_signing_key() -> str:
    """COMPLIANCE_SIGNING_KEY from env. Empty string is treated as unset."""
    return os.environ.get("COMPLIANCE_SIGNING_KEY", "") or ""


class SadTalkerProvider(LipSyncProvider):
    name: ClassVar[str] = "sadtalker"

    def __init__(
        self,
        *,
        models_root: Path | None = None,
        signing_key: str | None = None,
    ) -> None:
        self._models_root = models_root if models_root is not None else _resolve_models_root()
        self._signing_key = signing_key if signing_key is not None else _resolve_signing_key()

    # ------------------------------------------------------------- contract

    def required_assets(self) -> list[AssetSpec]:
        """Files SadTalker needs to load. See models/MODEL_CARDS.md for
        sha256 hashes (which Phase 3B will start verifying)."""
        return [
            AssetSpec(
                relative_path="checkpoints/mapping_00109-model.pth.tar",
                description="SadTalker audio→expression mapping checkpoint (109)",
                license_note="Apache-2.0 (verify at integration time)",
            ),
            AssetSpec(
                relative_path="checkpoints/mapping_00229-model.pth.tar",
                description="SadTalker audio→expression mapping checkpoint (229)",
                license_note="Apache-2.0",
            ),
            AssetSpec(
                relative_path="checkpoints/SadTalker_V0.0.2_256.safetensors",
                description="SadTalker 256px generator weights",
                license_note="Apache-2.0",
            ),
            AssetSpec(
                relative_path="checkpoints/SadTalker_V0.0.2_512.safetensors",
                description="SadTalker 512px generator weights",
                license_note="Apache-2.0",
            ),
            AssetSpec(
                relative_path="gfpgan/GFPGANv1.4.pth",
                description="GFPGAN face-restoration weights (post-process pass)",
                license_note="Apache-2.0 (GFPGAN — check ARCSoft clause)",
            ),
        ]

    def healthcheck(self) -> ProviderHealth:
        if self._models_root is None:
            return ProviderHealth(
                backend=self.name,
                status=ProviderHealthStatus.not_configured,
                errors=[
                    "Neither SADTALKER_MODELS_ROOT nor LIPSYNC_MODELS_ROOT is set. "
                    "Set one in .env (see docs/runbooks/model-management.md)."
                ],
            )
        if not self._models_root.exists():
            return ProviderHealth(
                backend=self.name,
                status=ProviderHealthStatus.missing_assets,
                models_root=str(self._models_root),
                missing_assets=[a.relative_path for a in self.required_assets()],
                errors=[f"models_root does not exist on disk: {self._models_root}"],
            )
        missing = [
            a.relative_path
            for a in self.required_assets()
            if not (self._models_root / a.relative_path).is_file()
        ]
        if missing:
            return ProviderHealth(
                backend=self.name,
                status=ProviderHealthStatus.missing_assets,
                models_root=str(self._models_root),
                missing_assets=missing,
                errors=[
                    f"{len(missing)} required SadTalker asset(s) missing under "
                    f"{self._models_root}; place them manually (no auto-download)."
                ],
            )
        return ProviderHealth(
            backend=self.name,
            status=ProviderHealthStatus.ok,
            models_root=str(self._models_root),
            extra={"phase": "3a_stub", "real_inference": False},
        )

    def validate_compliance_token(
        self,
        token: str,
        *,
        expected_job_id: str,
    ) -> ComplianceTokenClaims:
        if not self._signing_key:
            # No signing key configured: every token would verify against
            # an empty secret. Refuse explicitly rather than silently
            # accept anything.
            raise ComplianceTokenError(
                "COMPLIANCE_SIGNING_KEY not configured; refusing to validate tokens"
            )
        return verify_token(token, self._signing_key, expected_job_id=expected_job_id)

    async def synthesize(self, req: LipSyncRequest) -> LipSyncResult:
        """Phase 3A fail-fast synthesize.

        Order matters: validate the compliance token FIRST so a bad token
        never sees any provider state, then enforce asset presence, then
        explicitly refuse to proceed to inference.
        """
        # 1. Token first.
        self.validate_compliance_token(
            req.compliance_token, expected_job_id=str(req.job_id)
        )

        # 2. Assets must be present.
        health = self.healthcheck()
        if health.status is not ProviderHealthStatus.ok:
            raise MissingAssetsError(self.name, health.missing_assets)

        # 3. Phase 3A never runs real inference.
        raise ProviderNotImplementedError(
            "sadtalker: real inference lands in Phase 3B; "
            "Phase 3A only validates the contract + assets."
        )

    # =================================================================
    # Phase 7B — Readiness inspection (no real inference)
    #
    # Every method here is a pure check. None of them imports torch /
    # opencv / diffusers / SadTalker at module load. Imports happen
    # inside the methods so the default backend image (which has
    # **none** of those installed) can still call them.
    # =================================================================

    @staticmethod
    def inspect_runtime() -> dict:
        """Is the Python runtime SadTalker needs available?

        Today the only hard runtime dependency we probe for is ``torch``.
        ``importlib.util.find_spec`` doesn't import the module — it just
        checks whether the loader can find it, which keeps the default
        backend image torch-free.
        """
        try:
            torch_spec = importlib.util.find_spec("torch")
        except Exception as exc:  # pragma: no cover — defensive
            return {
                "torch_available": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {"torch_available": torch_spec is not None}

    def inspect_assets(self) -> dict:
        """Inspect the SadTalker weight directory.

        Returns ``{"status": "not_configured" | "missing" | "ok",
        "models_root": str | None, "missing": [list of relative paths]}``.

        Distinct from the legacy ``healthcheck()`` so callers don't have
        to translate ``ProviderHealthStatus`` enums into Phase 7B
        vocabulary.
        """
        if self._models_root is None:
            return {
                "status": "not_configured",
                "models_root": None,
                "missing": [a.relative_path for a in self.required_assets()],
            }
        if not self._models_root.exists():
            return {
                "status": "missing",
                "models_root": str(self._models_root),
                "missing": [a.relative_path for a in self.required_assets()],
            }
        missing = [
            a.relative_path
            for a in self.required_assets()
            if not (self._models_root / a.relative_path).is_file()
        ]
        if missing:
            return {
                "status": "missing",
                "models_root": str(self._models_root),
                "missing": missing,
            }
        return {
            "status": "ok",
            "models_root": str(self._models_root),
            "missing": [],
        }

    @staticmethod
    def inspect_gpu() -> dict:
        """Is a CUDA-visible device present *right now*?

        - If torch isn't installed → ``available=False, reason='torch_missing'``
          (the runtime check has more detail; this stays cheap).
        - If torch is installed but ``cuda.is_available()`` returns
          False → ``available=False, reason='no_cuda_device'``.
        - Otherwise → ``available=True, device_count=N, device_name=...``.
        """
        try:
            spec = importlib.util.find_spec("torch")
        except Exception as exc:  # pragma: no cover — defensive
            return {"available": False, "reason": "torch_probe_error", "error": str(exc)}
        if spec is None:
            return {"available": False, "reason": "torch_missing"}
        try:
            # Importing torch is heavy, so we only do it here, behind the
            # runtime gate. The default backend image never reaches this
            # line because the runtime probe above short-circuits it.
            import torch  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover — only on GPU hosts
            return {"available": False, "reason": "torch_import_failed", "error": str(exc)}
        try:
            if not torch.cuda.is_available():
                return {"available": False, "reason": "no_cuda_device"}
            count = int(torch.cuda.device_count())
            name = torch.cuda.get_device_name(0) if count else None
            return {"available": True, "device_count": count, "device_name": name}
        except Exception as exc:  # pragma: no cover — only on GPU hosts
            return {"available": False, "reason": "cuda_probe_failed", "error": str(exc)}

    def inspect_status(self) -> dict:
        """Combined Phase 7B readiness summary.

        Returns ``{"status": SadTalkerStatus, "details": {...}}``. The
        backend's ``/api/v1/video/generate`` and the provider catalog
        both call this — same vocabulary, single source of truth.

        Order of checks (deliberate):
        1. real-inference flags off → ``not_implemented`` (the most
           common state until Phase 7D enables real generation).
        2. assets missing             → ``assets_missing``
        3. torch unavailable          → ``runtime_missing``
        4. CUDA unavailable           → ``gpu_unavailable``
        5. everything present         → ``ready``

        Why ``not_implemented`` first? In Phase 7B we want operators to
        see "this provider isn't wired yet" even on a host that already
        has weights and a GPU — so the unanswered-question is always
        whether real-inference is gated on, not whether the host happens
        to be lucky.
        """
        assets = self.inspect_assets()
        runtime = self.inspect_runtime()
        gpu = self.inspect_gpu() if runtime.get("torch_available") else {
            "available": False,
            "reason": "torch_missing",
        }
        details = {"assets": assets, "runtime": runtime, "gpu": gpu}

        # Real-inference gate first: when the operator hasn't opted in,
        # the readiness state of weights / torch / CUDA is irrelevant to
        # the API surface — we always advertise ``not_implemented``. This
        # keeps Phase 6A's invariant ("known video providers return
        # not_implemented") true regardless of host quirks.
        if not _real_inference_enabled():
            return {"status": "not_implemented", "details": details}

        # Real-inference is on. Now the readiness story is the operator's
        # responsibility: report each gap with a specific code.
        if assets["status"] == "not_configured":
            return {"status": "not_configured", "details": details}
        if assets["status"] != "ok":
            return {"status": "assets_missing", "details": details}
        if not runtime.get("torch_available"):
            return {"status": "runtime_missing", "details": details}
        if not gpu.get("available"):
            return {"status": "gpu_unavailable", "details": details}
        return {"status": "ready", "details": details}

    # ----- generate() — Phase 7D: real inference behind a 7-gate fence -----

    def generate(
        self,
        *,
        image_path: str | Path,
        audio_path: str | Path,
        output_dir: str | Path,
        target_duration_seconds: int | None = None,
        model_id: str | None = None,
    ) -> dict:
        """Generate a talking-head MP4 — or refuse with a categorised code.

        Real generation requires **all seven** of:

        1. ``SADTALKER_ENABLE_REAL_INFERENCE=true``
        2. ``RUN_REAL_SADTALKER=1``
        3. ``SADTALKER_MODELS_ROOT`` set + weights on disk
        4. ``torch`` importable
        5. CUDA device visible
        6. input image path readable (caller responsibility)
        7. input audio path readable (caller responsibility)

        If any gate fails, returns a categorised failure dict without
        touching torch / opencv / SadTalker. The caller (the backend's
        ``/api/v1/video/generate``) translates the dict into the
        ``VideoGenerationResult`` shape.

        On success, writes the MP4 under ``output_dir`` and returns
        ``{"status": "completed", "output_path": <str>, ...}``.

        Cleanup contract: if the heavy path raises after creating
        partial files, we attempt to remove them before returning the
        failure dict.
        """
        # Gates 1 + 2.
        if not _real_inference_enabled():
            status = self.inspect_status()
            return {
                "status": "not_implemented",
                "error_code": "video_provider_not_implemented",
                "message": (
                    "SadTalker real inference is gated behind "
                    "SADTALKER_ENABLE_REAL_INFERENCE=true + "
                    "RUN_REAL_SADTALKER=1. Neither is currently set."
                ),
                "details": status["details"],
            }

        # Gates 3 + 4 + 5.
        status_info = self.inspect_status()
        if status_info["status"] != "ready":
            return {
                "status": status_info["status"],
                "error_code": _STATUS_TO_ERROR_CODE[status_info["status"]],
                "message": (
                    f"SadTalker not ready: status={status_info['status']}. "
                    "See inspect_status() details."
                ),
                "details": status_info["details"],
            }

        # Gates 6 + 7: the caller is responsible for ensuring the input
        # files exist, but we double-check here so a bad caller can't
        # silently corrupt a partial output.
        img = Path(image_path)
        aud = Path(audio_path)
        if not img.is_file():
            return {
                "status": "failed",
                "error_code": "video_generation_failed",
                "message": f"input image not found: {img}",
                "details": status_info["details"],
            }
        if not aud.is_file():
            return {
                "status": "failed",
                "error_code": "video_generation_failed",
                "message": f"input audio not found: {aud}",
                "details": status_info["details"],
            }

        # All seven gates satisfied. Delegate to the heavy path. This
        # is the **only** place in P1.AIVideo where real SadTalker
        # inference can happen. The function is module-level so tests
        # can monkeypatch it without touching the gate logic.
        return _attempt_real_inference(
            image_path=img,
            audio_path=aud,
            output_dir=Path(output_dir),
            target_duration_seconds=target_duration_seconds,
            model_id=model_id,
            details=status_info["details"],
        )


def _real_inference_enabled() -> bool:
    """Both env flags must be on. Either alone is insufficient.

    ``SADTALKER_ENABLE_REAL_INFERENCE`` is the configuration intent
    (does the operator *want* real inference?). ``RUN_REAL_SADTALKER``
    is the runtime arming switch (am I *actually* allowed to invoke it
    in this process?). Real generation only happens when both agree.
    """
    return _is_truthy(os.environ.get("SADTALKER_ENABLE_REAL_INFERENCE")) and _is_truthy(
        os.environ.get("RUN_REAL_SADTALKER")
    )


_STATUS_TO_ERROR_CODE: dict[str, str] = {
    "not_configured": "video_provider_not_configured",
    "runtime_missing": "video_runtime_missing",
    "assets_missing": "video_assets_missing",
    "gpu_unavailable": "video_gpu_missing",
    "not_implemented": "video_provider_not_implemented",
    "ready": "video_provider_not_implemented",
}


def _attempt_real_inference(
    *,
    image_path: Path,
    audio_path: Path,
    output_dir: Path,
    target_duration_seconds: int | None,
    model_id: str | None,
    details: dict,
) -> dict:
    """Phase 7D real inference path.

    All seven readiness gates have passed in the caller. This function:

    1. Lazy-imports the SadTalker library. If it isn't installed in the
       current image (the GPU image is ``INSTALL_SADTALKER_DEPS=false``
       by default), we surface ``video_runtime_missing``.
    2. Runs SadTalker against the image + audio, writes the MP4 under
       ``output_dir``.
    3. Returns a ``status="completed"`` dict on success, or a
       categorised failure on exception (after cleaning up partial
       files).

    Tests monkey-patch this function directly (see Phase 7D test file)
    so the success path is exercisable without GPU / weights.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    # Use a deterministic-ish name so the partial-cleanup path can find
    # the file again on failure.
    out_name = f"sadtalker_{uuid.uuid4().hex}.mp4"
    output_path = output_dir / out_name

    # Step 1: import the heavy library. We tolerate two missing-runtime
    # signatures — a missing top-level package (the most likely case)
    # and an ImportError from a sub-module (e.g. opencv missing).
    try:
        # Phase 7D: the real SadTalker library entry point is
        # ``sadtalker``. The package name on PyPI is also ``sadtalker``
        # but the upstream repo doesn't publish a wheel — operators
        # install from source. We import inside try/except so the
        # default image (which never installs it) cleanly returns
        # ``runtime_missing`` instead of crashing.
        import sadtalker  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as exc:
        return {
            "status": "runtime_missing",
            "error_code": "video_runtime_missing",
            "message": (
                f"SadTalker library not installed in this image: {exc}. "
                "Rebuild the GPU image with INSTALL_SADTALKER_DEPS=true "
                "and INSTALL_TORCH=true (Phase 7C/7D)."
            ),
            "details": details,
        }

    # Step 2: actually run inference. The real call lives in the
    # upstream SadTalker repo's `inference.py`; we wrap it so a hard
    # failure (CUDA OOM, broken weights, segfault re-raised as
    # RuntimeError) becomes a clean categorised response.
    try:
        # The pragma: no cover comments below mark code that only runs
        # on a host with SadTalker installed + a real GPU. Coverage
        # tooling on the default CI machine never reaches them; the
        # success-path test monkey-patches this whole function instead.
        from sadtalker.inference import run_inference  # type: ignore[import-not-found]  # pragma: no cover

        # pragma: no cover — only on GPU hosts
        run_inference(  # pragma: no cover
            image_path=str(image_path),
            audio_path=str(audio_path),
            output_path=str(output_path),
            target_duration_seconds=target_duration_seconds,
            model_id=model_id,
        )
    except ImportError as exc:
        # Partial install (e.g. sadtalker is importable but a submodule
        # isn't). Treat the same as runtime_missing — the operator
        # needs to fix their image.
        return {
            "status": "runtime_missing",
            "error_code": "video_runtime_missing",
            "message": f"SadTalker partially installed: {exc}",
            "details": details,
        }
    except Exception as exc:  # pragma: no cover — only on GPU hosts
        # Cleanup any partial MP4 the inference may have created.
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "status": "failed",
            "error_code": "video_generation_failed",
            "message": f"{type(exc).__name__}: {exc}",
            "details": details,
        }

    # Step 3: validate the output exists. If SadTalker reported success
    # but no file landed, surface that as a generation failure rather
    # than pretending it succeeded.
    if not output_path.is_file():  # pragma: no cover — only on GPU hosts
        return {
            "status": "failed",
            "error_code": "video_generation_failed",
            "message": "SadTalker returned without writing an MP4",
            "details": details,
        }

    return {  # pragma: no cover — only on GPU hosts
        "status": "completed",
        "output_path": str(output_path),
        "model_id": model_id,
        "target_duration_seconds": target_duration_seconds,
        "details": details,
    }
