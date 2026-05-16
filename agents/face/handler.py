"""Face — Phase 3E + Phase 9B.

Routing:

- ``face_mode == "provided_image"`` — validate the operator-supplied
  image: defense-in-depth path safety, then a stdlib-only header parse
  (PNG / JPEG / WebP) via ``common.image_validation``. Emit an
  ``ArtifactRef`` carrying real width, height, size, sha256, and
  mime_type. The DAG runner promotes refs with a checksum to the
  first-class ``artifacts`` table.

- ``face_mode is None`` (default) — Phase 9B removes the old
  ``portrait.png`` s3:// stub. No real SDXL / persona-LoRA provider is
  wired and no file is ever written, so the handler now emits a
  clearly-labelled placeholder ``ArtifactRef`` with
  ``extra.real_face_input=False`` and ``extra.is_placeholder=True`` —
  no ``.png`` URI, no ``local_path``, no ``checksum_sha256``, so the DAG
  runner cannot promote it to the artifacts table. Downstream lipsync
  keeps the legacy "portrait must exist" key check; the readiness
  gate inside lipsync already refuses to run real SadTalker without
  ``portrait.local_path``.

- Strict opt-in: if ``provider_selection.image_processor_id`` is set
  (other than the deterministic stdlib validator) or ``FACE_STRICT=1``,
  the default mode raises ``StageRejection(face_provider_not_implemented)``
  instead of soft-failing. Mirrors the Phase 8G-2 voice/TTS pattern.

Phase 9B does NOT implement face generation, identity matching, or
celebrity-likeness detection. The operator's ``consent_confirmed`` and
``synthetic_person_confirmed`` flags carry the compliance signal.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from common.enums import ArtifactType, StageName
from common.exceptions import StageRejection
from common.image_validation import validate_and_inspect_image
from common.path_safety import validate_local_image_path
from common.schemas import ArtifactRef, DagState, ImageRef, StageOutput


_DETERMINISTIC_IMAGE_PROCESSORS = {"stdlib_image_validation"}


def _placeholder_uri(job_id: str) -> str:
    return f"placeholder://face/{job_id}/no-real-face-input"


def _image_ref_to_uri(ref: ImageRef) -> str:
    if ref.type == "local_path":
        return Path(ref.path).as_uri()
    return ref.path


def _get_max_size_bytes() -> int | None:
    raw = os.environ.get("IMAGE_MAX_FILE_SIZE_BYTES")
    if not raw:
        return 10_485_760  # 10 MB default
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return 10_485_760


def _parse_optional_int(env_name: str) -> int | None:
    raw = os.environ.get(env_name, "")
    if not raw.strip():
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Mode handlers
# ---------------------------------------------------------------------------


def _strict_face_mode(state: DagState) -> bool:
    """Strict opt-in: explicit non-deterministic image_processor_id in
    provider_selection OR FACE_STRICT=1 env flag.

    Mirrors the Phase 8G-2 voice/TTS pattern: legacy DAG tests that
    don't set provider_selection keep the soft placeholder path; jobs
    that explicitly select a face provider get a clean StageRejection
    when no real provider is wired."""
    if os.environ.get("FACE_STRICT", "").strip().lower() in ("1", "true", "yes"):
        return True
    sel = state.provider_selection
    if not sel:
        return False
    pid: Any = sel.get("image_processor_id")
    if isinstance(pid, str) and pid.strip() and pid not in _DETERMINISTIC_IMAGE_PROCESSORS:
        return True
    return False


def _soft_noop_placeholder(state: DagState, *, reason: str, note: str) -> StageOutput:
    """Phase 9B placeholder portrait — clearly labelled metadata-only.

    Carries no ``.png`` URI, no ``local_path``, no ``checksum_sha256``
    so the DAG runner does NOT promote it to the artifacts table.
    Downstream stages keep the ``"portrait"`` key check working; the
    lipsync readiness gate already refuses to run real SadTalker
    without ``portrait.local_path``, so no phantom MP4 can be born
    from this ref."""
    portrait_ref = ArtifactRef(
        artifact_type=ArtifactType.image.value,
        uri=_placeholder_uri(str(state.job_id)),
        extra={
            "synthetic": True,
            "source": "placeholder",
            "phase": "phase9b_no_real_face_input",
            "real_face_input": False,
            "is_placeholder": True,
            "face_skip_reason": reason,
            "note": note,
        },
    )
    return StageOutput(
        noop=True,
        notes=note,
        artifacts={"portrait": portrait_ref},
    )


def _run_default_no_provider(state: DagState) -> StageOutput:
    """Default face_mode=None — no provider configured.

    Strict opt-in path: raise categorised StageRejection.
    Soft default path: emit a clearly-labelled placeholder so legacy
    metadata-only DAG tests stay green; lipsync gates real inference
    on portrait.local_path which the placeholder doesn't carry."""
    if not state.synthetic_person_confirmed:
        # Defensive: API + policy_gate already enforce this; we re-check
        # because the face stage is the one that would produce likeness.
        raise StageRejection(
            StageName.face.value, "synthetic_person_confirmed must be true"
        )

    if _strict_face_mode(state):
        raise StageRejection(
            StageName.face.value,
            (
                "face_provider_not_implemented: no real face/image provider "
                "is wired (image_processor_id={!r} requested or FACE_STRICT=1). "
                "Upload an image (face_mode='provided_image') or pick a "
                "deterministic image_processor_id."
            ).format((state.provider_selection or {}).get("image_processor_id")),
        )

    return _soft_noop_placeholder(
        state,
        reason="face_provider_not_configured",
        note=(
            "face no-op: no real face provider configured and no image "
            "uploaded; emitted placeholder (no real_face_input, no .png file)"
        ),
    )


def _run_provided_image(state: DagState) -> StageOutput:
    """Validate the operator-supplied image and emit a populated ArtifactRef."""
    ref = state.image_ref
    if ref is None:
        # Schema enforces this — handler defense in depth.
        raise StageRejection(
            StageName.face.value,
            "face_mode='provided_image' requires image_ref (handler check)",
        )

    if not ref.consent_confirmed:
        raise StageRejection(
            StageName.face.value,
            "image_ref.consent_confirmed must be true",
        )
    if not ref.synthetic_person_confirmed:
        raise StageRejection(
            StageName.face.value,
            "image_ref.synthetic_person_confirmed must be true "
            "(real-person likeness without consent is not allowed)",
        )

    image_meta = None
    local_path: str | None = None
    if ref.type == "local_path":
        try:
            validate_local_image_path(ref.path)
        except ValueError as exc:
            raise StageRejection(StageName.face.value, str(exc)) from exc

        try:
            image_meta = validate_and_inspect_image(
                ref.path,
                mime_type=ref.mime_type,
                max_size_bytes=_get_max_size_bytes(),
                min_width=_parse_optional_int("IMAGE_MIN_WIDTH"),
                min_height=_parse_optional_int("IMAGE_MIN_HEIGHT"),
            )
        except ValueError as exc:
            raise StageRejection(StageName.face.value, str(exc)) from exc
        local_path = str(image_meta.path)

    portrait_ref = ArtifactRef(
        artifact_type=ArtifactType.image.value,
        uri=_image_ref_to_uri(ref),
        local_path=local_path,
        mime_type=ref.mime_type,
        checksum_sha256=(
            image_meta.checksum_sha256 if image_meta else ref.checksum
        ),
        size_bytes=image_meta.size_bytes if image_meta else None,
        width=image_meta.width if image_meta else None,
        height=image_meta.height if image_meta else None,
        extra={
            "source": "provided_image",
            "ref_type": ref.type,
            "format": image_meta.format if image_meta else None,
            "inspected": image_meta is not None,
            "phase": "phase9b_provided_image",
            "real_face_input": True,
            "is_placeholder": False,
            "synthetic_person_confirmed": True,
            "consent_confirmed": True,
        },
    )
    return StageOutput(
        noop=False,
        notes="face mode='provided_image': validated image header; no generation",
        artifacts={"portrait": portrait_ref},
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run(state: DagState) -> StageOutput:
    if state.face_mode == "provided_image":
        return _run_provided_image(state)
    if state.face_mode is None:
        return _run_default_no_provider(state)
    raise StageRejection(
        StageName.face.value, f"unsupported face_mode={state.face_mode!r}"
    )
