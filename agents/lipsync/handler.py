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

    # Phase 7E: provider-aware dispatch. ``sadtalker`` was the first
    # provider wired end-to-end. Phase 12Y adds wav2lip / musetalk /
    # echomimic / hallo via the unified HTTP wrapper dispatch table.
    # Text-to-video providers (svd, animatediff, ltx_video, hunyuan_video,
    # mochi) and LivePortrait remain no-op stubs because they need a
    # different upstream input contract (no audio, or a driving video
    # instead of audio).
    video_provider_id = _resolve_video_provider_id(state, expected_backend)

    if (
        video_provider_id in _HTTP_LIPSYNC_DISPATCH
        and video_provider_id != "sadtalker"
        and os.environ.get(_HTTP_LIPSYNC_DISPATCH[video_provider_id]["env_url"], "").strip()
    ):
        # Phase 12Y — wrapper is reachable, dispatch via HTTP.
        return await _run_http_lipsync_via_wrapper(
            provider_id=video_provider_id,
            state=state,
            voice_output=voice_output,
            face_output=face_output,
            expected_backend=expected_backend,
        )

    if (
        video_provider_id in _HTTP_VIDEOGEN_DISPATCH
        and os.environ.get(_HTTP_VIDEOGEN_DISPATCH[video_provider_id]["env_url"], "").strip()
    ):
        # Phase 12V — text-to-video / image-to-video wrapper. Different
        # input contract from lipsync (no audio for txt→vid; just an
        # image for SVD), so we run a separate dispatcher.
        return await _run_http_videogen_via_wrapper(
            provider_id=video_provider_id,
            state=state,
            face_output=face_output,
            expected_backend=expected_backend,
        )

    if video_provider_id != "sadtalker":
        # Either an unknown provider, a wrapper without BASE_URL configured,
        # or a text-to-video provider whose wrapper is not running.
        # Preserve the Phase 3A no-op stub so the job pipeline keeps moving.
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
        #
        # Phase 11E — format the reason as
        # ``<error_code>: <operator_message>`` so the frontend can
        # branch on the leading code (e.g. ``video_face_landmark_missing``)
        # and render a localized recovery message. The raw subprocess
        # tail lives in the provider's ``details`` metadata for the
        # diagnostics panel; the operator-visible ``rejection_reason``
        # stays short and human.
        error_code = result.get("error_code") or "video_generation_failed"
        op_msg = result.get("message") or "<no message>"
        raise StageRejection(
            StageName.lipsync.value,
            f"{error_code}: {op_msg}",
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


# ---------------------------------------------------------------------------
# Phase 12Y — unified HTTP dispatch for the new lipsync wrappers
#
# Each entry maps the provider_id to:
#   - env_url:        env var holding the wrapper base URL
#   - env_timeout:    env var holding the HTTP read timeout (seconds)
#   - default_timeout: fallback timeout when env_timeout is unset
#   - endpoint:       POST path on the wrapper (image+audio → MP4)
#   - body_extra:     extra request-body kwargs the wrapper expects
#
# All four wrappers share the same minimal contract: image_path +
# audio_path + output_path. Per-provider tuning knobs live in body_extra.
# LivePortrait is intentionally excluded — its wrapper takes
# source_image + driving_video instead of audio, which does not fit
# the lipsync upstream contract (voice → narration audio).
# ---------------------------------------------------------------------------

_HTTP_LIPSYNC_DISPATCH: dict[str, dict[str, Any]] = {
    "sadtalker": {
        "env_url": "SADTALKER_BASE_URL",
        "env_timeout": "SADTALKER_HTTP_TIMEOUT",
        "default_timeout": 1800,
        "endpoint": "/sadtalker/generate",
        "body_extra": {
            "size": 256,
            "enhancer": "gfpgan",
            "preprocess": "crop",
            "still": True,
        },
    },
    "wav2lip": {
        "env_url": "WAV2LIP_BASE_URL",
        "env_timeout": "WAV2LIP_HTTP_TIMEOUT",
        "default_timeout": 900,
        "endpoint": "/wav2lip/generate",
        "body_extra": {"checkpoint": "wav2lip_gan"},
    },
    "musetalk": {
        "env_url": "MUSETALK_BASE_URL",
        "env_timeout": "MUSETALK_HTTP_TIMEOUT",
        "default_timeout": 900,
        "endpoint": "/musetalk/generate",
        "body_extra": {"fps": 25},
    },
    "echomimic": {
        "env_url": "ECHOMIMIC_BASE_URL",
        "env_timeout": "ECHOMIMIC_HTTP_TIMEOUT",
        "default_timeout": 1500,
        "endpoint": "/echomimic/generate",
        "body_extra": {},
    },
    "hallo": {
        "env_url": "HALLO_BASE_URL",
        "env_timeout": "HALLO_HTTP_TIMEOUT",
        "default_timeout": 1800,
        "endpoint": "/hallo/generate",
        "body_extra": {},
    },
}


async def _run_http_lipsync_via_wrapper(
    *,
    provider_id: str,
    state: DagState,
    voice_output: StageOutput,
    face_output: StageOutput,
    expected_backend: str,
) -> StageOutput:
    """Generic POST → /<provider>/generate dispatch for Phase 12Y wrappers.

    Mirrors the SadTalker proxy path: posts {image_path, audio_path,
    output_path, ...} to the wrapper, expects ``{"status": "completed",
    "output_path": ..., "size_bytes": ..., "duration_seconds": ...}``,
    and wraps the MP4 in a ``talking_head`` ``ArtifactRef``. Any
    non-completed wrapper response is translated into a categorised
    ``StageRejection`` so the orchestrator records the failure in the
    same vocabulary as SadTalker.
    """
    import json
    import urllib.error
    import urllib.request
    import uuid as _uuid

    spec = _HTTP_LIPSYNC_DISPATCH[provider_id]
    base_url = os.environ.get(spec["env_url"], "").strip()
    if not base_url:
        raise StageRejection(
            StageName.lipsync.value,
            (
                f"video_provider_not_configured: {provider_id} requires "
                f"{spec['env_url']} to point at the model-{provider_id} wrapper."
            ),
        )

    portrait = face_output.artifacts["portrait"]
    narration = voice_output.artifacts["narration"]
    img_path = portrait.local_path
    aud_path = narration.local_path
    if not img_path or not aud_path:
        raise StageRejection(
            StageName.lipsync.value,
            (
                f"upstream face/voice artifacts do not carry local_path; "
                f"{provider_id} HTTP wrapper needs on-disk files. "
                f"face.local_path={img_path!r}, voice.local_path={aud_path!r}"
            ),
        )

    base_root = os.environ.get("ARTIFACTS_LOCAL_ROOT") or tempfile.gettempdir()
    out_dir = Path(base_root) / "video" / str(state.job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        out_dir.chmod(0o777)
    except OSError:
        pass
    out_name = f"{provider_id}_{_uuid.uuid4().hex}.mp4"
    out_path = out_dir / out_name

    body: dict[str, Any] = {
        "image_path": str(img_path),
        "audio_path": str(aud_path),
        "output_path": str(out_path),
    }
    body.update(spec["body_extra"])

    url = base_url.rstrip("/") + spec["endpoint"]
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    timeout = int(os.environ.get(spec["env_timeout"], str(spec["default_timeout"])))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload_bytes = resp.read()
    except urllib.error.HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="replace")[:500]
        raise StageRejection(
            StageName.lipsync.value,
            f"video_generation_failed: {provider_id} wrapper HTTP {exc.code}: {err_text}",
        ) from exc
    except urllib.error.URLError as exc:
        raise StageRejection(
            StageName.lipsync.value,
            (
                f"video_runtime_missing: {provider_id} wrapper unreachable at "
                f"{base_url!r}: {type(exc).__name__}: {getattr(exc, 'reason', exc)}"
            ),
        ) from exc

    try:
        wrapper = json.loads(payload_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StageRejection(
            StageName.lipsync.value,
            f"video_generation_failed: {provider_id} wrapper returned malformed JSON: {exc}",
        ) from exc

    if wrapper.get("status") != "completed":
        ec = wrapper.get("error_code") or "video_generation_failed"
        msg = wrapper.get("message") or wrapper.get("detail") or wrapper.get("status")
        raise StageRejection(
            StageName.lipsync.value,
            f"{ec}: {provider_id} {msg}",
        )

    final_path = Path(wrapper.get("output_path") or out_path)
    if not final_path.is_file() or final_path.stat().st_size == 0:
        raise StageRejection(
            StageName.lipsync.value,
            (
                f"video_generation_failed: {provider_id} wrapper reported completed "
                f"but {final_path} is missing/empty."
            ),
        )

    size_bytes = final_path.stat().st_size
    h = hashlib.sha256()
    with final_path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    checksum = h.hexdigest()

    talking_head_ref = ArtifactRef(
        artifact_type="video",
        uri=final_path.as_uri(),
        local_path=str(final_path),
        mime_type="video/mp4",
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        duration_seconds=wrapper.get("duration_seconds"),
        width=wrapper.get("width"),
        height=wrapper.get("height"),
        extra={
            "fps": wrapper.get("fps") or 25,
            "backend": provider_id,
            "phase": "phase12y_http_wrapper",
            "wrapper_base_url": base_url,
            "wrapper_metadata": {k: v for k, v in wrapper.items()
                                  if k not in {"status", "output_path"}},
        },
    )
    return StageOutput(
        noop=False,
        notes=(
            f"lipsync: {provider_id} (HTTP wrapper) produced "
            f"{size_bytes} bytes at {final_path}"
        ),
        artifacts={"talking_head": talking_head_ref},
        extra={
            provider_id: {
                "inspect_status": "ready",
                "wrapper_base_url": base_url,
                "wrapper_endpoint": spec["endpoint"],
            }
        },
    )


# ---------------------------------------------------------------------------
# Phase 12V — text-to-video / image-to-video dispatch
#
# These providers do NOT take a narration audio input; they synthesize
# motion either from a single image (SVD) or from a text prompt
# (AnimateDiff / LTX-Video / HunyuanVideo / Mochi). Each entry declares:
#
#   - env_url + env_timeout + default_timeout: same shape as lipsync
#   - endpoint: POST path on the wrapper
#   - input_kind: "image_only" (uses face portrait) or "prompt_only"
#                  (uses script_text / brief)
#   - body_extra: per-provider tuning knobs
#
# Output contract identical to lipsync: wrapper writes MP4 at
# ``output_path``, returns ``{"status": "completed", "output_path": ...}``.
# The handler registers the MP4 as a ``talking_head`` ArtifactRef so
# downstream stages (editor, qc, publisher) treat it like any other
# generated video.
# ---------------------------------------------------------------------------

_HTTP_VIDEOGEN_DISPATCH: dict[str, dict[str, Any]] = {
    "svd": {
        "env_url": "SVD_BASE_URL",
        "env_timeout": "SVD_HTTP_TIMEOUT",
        "default_timeout": 600,
        "endpoint": "/svd/generate",
        "input_kind": "image_only",
        "body_extra": {"num_frames": 25, "fps": 7, "motion_bucket_id": 127},
    },
    "animatediff": {
        "env_url": "ANIMATEDIFF_BASE_URL",
        "env_timeout": "ANIMATEDIFF_HTTP_TIMEOUT",
        "default_timeout": 900,
        "endpoint": "/animatediff/generate",
        "input_kind": "prompt_only",
        "body_extra": {"num_frames": 16, "fps": 8, "steps": 25, "guidance_scale": 7.5},
    },
    "ltx_video": {
        "env_url": "LTX_BASE_URL",
        "env_timeout": "LTX_HTTP_TIMEOUT",
        "default_timeout": 600,
        "endpoint": "/ltx/generate",
        "input_kind": "prompt_only",
        "body_extra": {"num_frames": 121, "fps": 24, "steps": 40, "guidance_scale": 3.0},
    },
    "hunyuan_video": {
        "env_url": "HUNYUAN_BASE_URL",
        "env_timeout": "HUNYUAN_HTTP_TIMEOUT",
        "default_timeout": 1800,
        "endpoint": "/hunyuan/generate",
        "input_kind": "prompt_only",
        "body_extra": {"num_frames": 65, "fps": 24, "steps": 30, "guidance_scale": 6.0},
    },
    "mochi": {
        "env_url": "MOCHI_BASE_URL",
        "env_timeout": "MOCHI_HTTP_TIMEOUT",
        "default_timeout": 1800,
        "endpoint": "/mochi/generate",
        "input_kind": "prompt_only",
        "body_extra": {"num_frames": 84, "fps": 30, "steps": 64, "guidance_scale": 4.5},
    },
}


def _resolve_videogen_prompt(state: DagState) -> str:
    """Pick a prompt for text-to-video providers — script wins, brief
    is the fallback. Truncate to 4000 chars (the wrappers' Pydantic max)."""
    text = (state.script_text or state.brief or "").strip()
    return text[:4000] or "A cinematic short of a person speaking, soft lighting."


async def _run_http_videogen_via_wrapper(
    *,
    provider_id: str,
    state: DagState,
    face_output: StageOutput,
    expected_backend: str,
) -> StageOutput:
    """Generic POST → /<provider>/generate dispatch for text-to-video
    and image-to-video wrappers (Phase 12V)."""
    import json
    import urllib.error
    import urllib.request
    import uuid as _uuid

    spec = _HTTP_VIDEOGEN_DISPATCH[provider_id]
    base_url = os.environ.get(spec["env_url"], "").strip()
    if not base_url:
        raise StageRejection(
            StageName.lipsync.value,
            (
                f"video_provider_not_configured: {provider_id} requires "
                f"{spec['env_url']} to point at the model-{provider_id} wrapper."
            ),
        )

    base_root = os.environ.get("ARTIFACTS_LOCAL_ROOT") or tempfile.gettempdir()
    out_dir = Path(base_root) / "video" / str(state.job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        out_dir.chmod(0o777)
    except OSError:
        pass
    out_name = f"{provider_id}_{_uuid.uuid4().hex}.mp4"
    out_path = out_dir / out_name

    body: dict[str, Any] = {"output_path": str(out_path)}
    if spec["input_kind"] == "image_only":
        portrait = face_output.artifacts["portrait"]
        if not portrait.local_path:
            raise StageRejection(
                StageName.lipsync.value,
                (
                    f"video_generation_failed: {provider_id} (image-only) needs "
                    f"face portrait local_path but got None."
                ),
            )
        body["image_path"] = str(portrait.local_path)
    elif spec["input_kind"] == "prompt_only":
        body["prompt"] = _resolve_videogen_prompt(state)
    body.update(spec["body_extra"])

    url = base_url.rstrip("/") + spec["endpoint"]
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    timeout = int(os.environ.get(spec["env_timeout"], str(spec["default_timeout"])))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload_bytes = resp.read()
    except urllib.error.HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="replace")[:500]
        raise StageRejection(
            StageName.lipsync.value,
            f"video_generation_failed: {provider_id} wrapper HTTP {exc.code}: {err_text}",
        ) from exc
    except urllib.error.URLError as exc:
        raise StageRejection(
            StageName.lipsync.value,
            (
                f"video_runtime_missing: {provider_id} wrapper unreachable at "
                f"{base_url!r}: {type(exc).__name__}: {getattr(exc, 'reason', exc)}"
            ),
        ) from exc

    try:
        wrapper = json.loads(payload_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StageRejection(
            StageName.lipsync.value,
            f"video_generation_failed: {provider_id} wrapper returned malformed JSON: {exc}",
        ) from exc

    if wrapper.get("status") != "completed":
        ec = wrapper.get("error_code") or "video_generation_failed"
        msg = wrapper.get("message") or wrapper.get("detail") or wrapper.get("status")
        raise StageRejection(
            StageName.lipsync.value,
            f"{ec}: {provider_id} {msg}",
        )

    final_path = Path(wrapper.get("output_path") or out_path)
    if not final_path.is_file() or final_path.stat().st_size == 0:
        raise StageRejection(
            StageName.lipsync.value,
            (
                f"video_generation_failed: {provider_id} wrapper reported completed "
                f"but {final_path} is missing/empty."
            ),
        )

    size_bytes = final_path.stat().st_size
    h = hashlib.sha256()
    with final_path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    checksum = h.hexdigest()

    talking_head_ref = ArtifactRef(
        artifact_type="video",
        uri=final_path.as_uri(),
        local_path=str(final_path),
        mime_type="video/mp4",
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        duration_seconds=wrapper.get("duration_seconds"),
        width=wrapper.get("width"),
        height=wrapper.get("height"),
        extra={
            "fps": wrapper.get("fps") or spec["body_extra"].get("fps") or 25,
            "backend": provider_id,
            "phase": "phase12v_http_videogen_wrapper",
            "input_kind": spec["input_kind"],
            "wrapper_base_url": base_url,
            "wrapper_metadata": {k: v for k, v in wrapper.items()
                                  if k not in {"status", "output_path"}},
        },
    )
    return StageOutput(
        noop=False,
        notes=(
            f"lipsync: {provider_id} ({spec['input_kind']} HTTP wrapper) produced "
            f"{size_bytes} bytes at {final_path}"
        ),
        artifacts={"talking_head": talking_head_ref},
        extra={
            provider_id: {
                "inspect_status": "ready",
                "wrapper_base_url": base_url,
                "wrapper_endpoint": spec["endpoint"],
                "input_kind": spec["input_kind"],
            }
        },
    )
