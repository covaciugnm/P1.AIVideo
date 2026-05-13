"""Face — Phase 3E: validate provided portrait images.

Routing:

- ``face_mode is None`` (default) — emit the same Phase 2 stub portrait
  reference; preserves every test from Phase 1 through Phase 3D that
  didn't opt into a face input mode. No real synthesis happens.
- ``face_mode == "provided_image"`` — validate the operator-supplied
  image: defense-in-depth path safety, then a stdlib-only header parse
  (PNG / JPEG / WebP) via ``common.image_validation``. Emit an
  ``ArtifactRef`` carrying real width, height, size, sha256, and
  mime_type. The DAG runner promotes refs with a checksum to the
  first-class ``artifacts`` table.

Phase 3E does NOT implement face generation, identity matching, or
celebrity-likeness detection. The operator's ``consent_confirmed`` and
``synthetic_person_confirmed`` flags carry the compliance signal.
"""
from __future__ import annotations

import os
from pathlib import Path

from common.enums import ArtifactType, StageName
from common.exceptions import StageRejection
from common.image_validation import validate_and_inspect_image
from common.path_safety import validate_local_image_path
from common.schemas import ArtifactRef, DagState, ImageRef, StageOutput


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


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


def _run_stub(state: DagState) -> StageOutput:
    """Phase 2 stub portrait — no face input declared."""
    if not state.synthetic_person_confirmed:
        # Defensive: API + policy_gate already enforce this; we re-check
        # because the face stage is the one that would produce likeness.
        raise StageRejection(
            StageName.face.value, "synthetic_person_confirmed must be true"
        )

    portrait_ref = ArtifactRef(
        artifact_type=ArtifactType.image.value,
        uri=_stub_uri(str(state.job_id), "portrait.png"),
        extra={
            "synthetic": True,
            "source": "stub",
            "phase": "phase3e_stub",
        },
    )
    return StageOutput(
        noop=True,
        notes="face no-op: real SDXL + persona LoRA lands in a later phase",
        artifacts={"portrait": portrait_ref},
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
            "phase": "phase3e",
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
        return _run_stub(state)
    raise StageRejection(
        StageName.face.value, f"unsupported face_mode={state.face_mode!r}"
    )
