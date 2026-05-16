"""LipSync stage handler.

Phase 2 (no-op): verifies the compliance token, validates upstream
voice + face artifacts, emits a stub ``talking_head.mp4`` reference.

Phase 7E (provider-aware): reads ``state.provider_selection`` to route
to the right video provider. For ``sadtalker``:

- ``inspect_status() == "not_implemented"`` (default, gate off) →
  preserve the Phase 2 no-op stub so every earlier-phase test stays
  green.
- ``inspect_status() == "ready"`` → call the real-inference hook. The
  hook is module-level so tests monkeypatch it without touching the
  gate logic. On ``completed`` the handler builds a video ``ArtifactRef``
  carrying the local path + checksum so downstream QC/publisher
  consumers can read it.
- Any other status (``not_configured`` / ``assets_missing`` /
  ``runtime_missing`` / ``gpu_unavailable``) raises ``StageRejection``
  with a categorised reason — the DAG records the failure cleanly,
  the job stops without crashing.

The handler does **not** import torch, opencv, or any SadTalker
library at module load. The heavy import lives behind the real-
inference path, which only runs when every Phase 7D gate is open.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from common.enums import StageName
from common.exceptions import ComplianceTokenError, StageRejection
from common.schemas import ArtifactRef, DagState, StageOutput

from agents.compliance_officer.compliance_token import verify_token


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


def _resolve_video_provider_id(state: DagState, expected_backend: str) -> str:
    """Per-job ``provider_selection`` wins; otherwise the deploy
    default (``cfg.allowed_lipsync_backend`` → ``expected_backend``)."""
    if state.provider_selection:
        pid = state.provider_selection.get("video_provider_id")
        if isinstance(pid, str) and pid.strip():
            return pid
    return expected_backend


def _noop_stub_output(
    *,
    expected_backend: str,
    provider_status: dict[str, Any] | None,
    job_id: str,
) -> StageOutput:
    """Phase 2 stub-shape output. Same artifacts, slightly richer
    ``extra`` block when the Phase 7B inspection ran."""
    talking_head_ref = ArtifactRef(
        artifact_type="video",
        uri=_stub_uri(job_id, "talking_head.mp4"),
        extra={
            "fps": 25,
            "backend": expected_backend,
            "phase": "phase2_noop",
        },
    )
    extra: dict[str, Any] = {}
    if provider_status is not None:
        extra["sadtalker"] = {
            "inspect_status": provider_status.get("status"),
            "details": provider_status.get("details", {}),
        }
    return StageOutput(
        noop=True,
        notes=(
            f"lipsync no-op: real {expected_backend} integration is "
            "wired but the real-inference gate is off"
        ),
        artifacts={"talking_head": talking_head_ref},
        extra=extra,
    )


async def run(
    state: DagState,
    *,
    signing_key: str,
    expected_backend: str,
) -> StageOutput:
    # Token verification first — refuse before any other work.
    if not state.compliance_token:
        raise StageRejection(
            StageName.lipsync.value,
            "missing compliance_token: pre_lipsync_auth must run first",
        )
    try:
        claims = verify_token(
            state.compliance_token,
            signing_key,
            expected_job_id=str(state.job_id),
        )
    except ComplianceTokenError as exc:
        raise StageRejection(
            StageName.lipsync.value, f"compliance_token invalid: {exc}"
        ) from exc

    if claims.allowed_lipsync_backend != expected_backend:
        raise StageRejection(
            StageName.lipsync.value,
            f"token authorizes backend={claims.allowed_lipsync_backend!r}, "
            f"runner is configured for {expected_backend!r}",
        )

    # Now validate upstream artifacts.
    voice_output = state.stage_outputs.get(StageName.voice.value)
    face_output = state.stage_outputs.get(StageName.face.value)
    if voice_output is None or "narration" not in voice_output.artifacts:
        raise StageRejection(StageName.lipsync.value, "upstream voice missing narration")
    if face_output is None or "portrait" not in face_output.artifacts:
        raise StageRejection(StageName.lipsync.value, "upstream face missing portrait")

    # Phase 7E: provider-aware dispatch. ``sadtalker`` is the first
    # provider we wire end-to-end; other providers stay no-op stubs
    # (their hardened adapters land in later phases mirroring the
    # SadTalker work).
    video_provider_id = _resolve_video_provider_id(state, expected_backend)

    if video_provider_id != "sadtalker":
        return _noop_stub_output(
            expected_backend=expected_backend,
            provider_status=None,
            job_id=str(state.job_id),
        )

    from agents.lipsync.providers.sadtalker.provider import SadTalkerProvider

    provider = SadTalkerProvider()
    status_info = provider.inspect_status()
    status = status_info["status"]

    if status == "not_implemented":
        # Default state: real-inference flags off. Preserve Phase 2
        # no-op so every earlier test (phase 2, 3, 4, 5, 6) stays
        # exactly as it was. Embed the inspection result for telemetry.
        return _noop_stub_output(
            expected_backend=expected_backend,
            provider_status=status_info,
            job_id=str(state.job_id),
        )

    if status in (
        "not_configured",
        "assets_missing",
        "runtime_missing",
        "gpu_unavailable",
    ):
        # The operator has opted in to real inference but something
        # required is missing. Reject the stage with a categorised
        # reason — the DAG records the failure, the job stops, no
        # phantom artifact is registered.
        raise StageRejection(
            StageName.lipsync.value,
            (
                f"sadtalker {status}: see docs/runbooks/sadtalker-runtime.md. "
                f"details={status_info.get('details', {})}"
            ),
        )

    # status == "ready" — every readiness gate is green. Hand off to
    # the real-inference hook (module-level so tests monkeypatch it).
    return await _attempt_lipsync_inference(
        state=state,
        provider=provider,
        voice_output=voice_output,
        face_output=face_output,
        expected_backend=expected_backend,
        status_info=status_info,
    )


async def _attempt_lipsync_inference(
    *,
    state: DagState,
    provider,
    voice_output: StageOutput,
    face_output: StageOutput,
    expected_backend: str,
    status_info: dict[str, Any],
) -> StageOutput:
    """Phase 7E real-inference handoff.

    Sources the image + audio local paths from the upstream stage
    outputs, calls ``provider.generate()``, and wraps the result in a
    ``StageOutput``. Module-level so tests monkeypatch it without
    touching the readiness logic above.
    """
    portrait = face_output.artifacts["portrait"]
    narration = voice_output.artifacts["narration"]
    img_path = portrait.local_path
    aud_path = narration.local_path
    if not img_path or not aud_path:
        raise StageRejection(
            StageName.lipsync.value,
            (
                "upstream face/voice artifacts do not carry local_path; "
                "real SadTalker inference needs on-disk files. "
                f"face.local_path={img_path!r}, voice.local_path={aud_path!r}"
            ),
        )

    # Output dir: pull from env if set (matches the backend's
    # ARTIFACTS_LOCAL_ROOT convention), otherwise fall back to a
    # process-local tmp area so a dev run without that env still works.
    base_root = os.environ.get("ARTIFACTS_LOCAL_ROOT") or tempfile.gettempdir()
    out_dir = Path(base_root) / "video" / str(state.job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Mirror the backend's video.py fix: widen perms so an out-of-process
    # sadtalker wrapper (Phase 10B, uid 10002) can shutil.move the MP4
    # into this per-job dir regardless of whether the orchestrator
    # (uid 1000) created it. Single-uid setups are unaffected.
    try:
        out_dir.chmod(0o777)
    except OSError:
        pass

    result = provider.generate(
        image_path=img_path,
        audio_path=aud_path,
        output_dir=str(out_dir),
        target_duration_seconds=state.target_duration_seconds,
    )
    if result.get("status") != "completed":
        # The provider already cleaned up partial files; we just
        # translate the categorised failure into a StageRejection.
        raise StageRejection(
            StageName.lipsync.value,
            (
                f"sadtalker generation returned status={result.get('status')!r}, "
                f"error_code={result.get('error_code')!r}: "
                f"{result.get('message', '<no message>')}"
            ),
        )

    output_path = Path(result["output_path"])
    if not output_path.is_file():
        raise StageRejection(
            StageName.lipsync.value,
            f"sadtalker reported success but {output_path} is not on disk",
        )
    size_bytes = output_path.stat().st_size
    h = hashlib.sha256()
    with output_path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    checksum = h.hexdigest()

    talking_head_ref = ArtifactRef(
        artifact_type="video",
        uri=output_path.as_uri(),
        local_path=str(output_path),
        mime_type="video/mp4",
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        duration_seconds=result.get("duration_seconds"),
        width=result.get("width"),
        height=result.get("height"),
        extra={
            "fps": 25,
            "backend": expected_backend,
            "phase": "phase7e_real_inference",
            "sadtalker": {
                "inspect_status": "ready",
                "details": status_info.get("details", {}),
                "model_id": result.get("model_id"),
            },
        },
    )
    return StageOutput(
        noop=False,
        notes=(
            f"lipsync: {expected_backend} produced "
            f"{size_bytes} bytes at {output_path}"
        ),
        artifacts={"talking_head": talking_head_ref},
        extra={
            "sadtalker": {
                "inspect_status": "ready",
                "details": status_info.get("details", {}),
            }
        },
    )
