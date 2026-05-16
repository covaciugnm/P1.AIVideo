"""Phase 9B — face stage stops emitting fake ``portrait.png``.

Pins:
- ``face_mode="provided_image"`` returns a real ArtifactRef with
  ``local_path``, ``checksum_sha256``, width/height (Phase 3E contract
  preserved).
- ``face_mode=None`` no longer emits a ``portrait.png`` URI. Instead the
  handler returns a clearly-labelled placeholder
  ``ArtifactRef`` with ``extra.real_face_input=False``,
  ``extra.is_placeholder=True``, no ``.png`` URI, no ``local_path``,
  no ``checksum_sha256`` — so the DAG runner cannot promote it to the
  artifacts table.
- Strict opt-in via ``provider_selection.image_processor_id`` (non-
  deterministic) OR ``FACE_STRICT=1`` env makes the default path raise
  ``face_provider_not_implemented`` instead of soft-failing.
- Unsafe local image paths are rejected.
- The synthetic/consent attestation is still enforced.
- Module load does not pull PIL / cv2 / torch / onnxruntime — Phase 3E
  invariant preserved.
"""
from __future__ import annotations

import struct
import sys
import uuid
import zlib
from pathlib import Path

import pytest


def _make_min_png_bytes(width: int = 512, height: int = 512) -> bytes:
    """Construct a minimal valid PNG with the requested dimensions.

    Stdlib-only — keeps the test independent of PIL so we can also assert
    that loading the face handler doesn't pull image libraries."""

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            len(data).to_bytes(4, "big")
            + tag
            + data
            + zlib.crc32(tag + data).to_bytes(4, "big")
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    # Single-row uncompressed IDAT — a real decoder will reject only on
    # full inflate; our header parser doesn't read pixels.
    idat = zlib.compress(b"\x00" + b"\x00\x00\x00" * width)
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def _make_state(
    *,
    face_mode: str | None = None,
    provider_selection: dict | None = None,
    image_path: str | None = None,
):
    from common.schemas import DagState, ImageRef

    image_ref = None
    if image_path is not None:
        image_ref = ImageRef(
            type="local_path",
            path=image_path,
            mime_type="image/png",
            consent_confirmed=True,
            synthetic_person_confirmed=True,
        )

    return DagState(
        job_id=uuid.uuid4(),
        brief="Phase 9B face stage smoke",
        target_duration_seconds=30,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
        face_mode=face_mode,
        image_ref=image_ref,
        provider_selection=provider_selection,
    )


# ---------------------------------------------------------------------------
# Phase 3E preservation: provided_image still emits a real ArtifactRef.
# ---------------------------------------------------------------------------


async def test_provided_image_emits_real_artifact_ref(tmp_path: Path, monkeypatch):
    from agents.face.handler import run as face_run

    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(tmp_path))
    img_path = tmp_path / "synthetic_portrait.png"
    img_path.write_bytes(_make_min_png_bytes(512, 512))

    state = _make_state(
        face_mode="provided_image",
        image_path=str(img_path),
    )
    out = await face_run(state)
    assert out.noop is False
    portrait = out.artifacts["portrait"]
    assert portrait.local_path == str(img_path)
    assert portrait.checksum_sha256 and len(portrait.checksum_sha256) == 64
    assert portrait.size_bytes and portrait.size_bytes > 0
    assert portrait.width == 512
    assert portrait.height == 512
    assert portrait.mime_type == "image/png"
    assert portrait.extra["real_face_input"] is True
    assert portrait.extra["is_placeholder"] is False
    assert portrait.extra["source"] == "provided_image"
    # The URI must NOT be the legacy fake portrait.png stub.
    assert "placeholder://" not in portrait.uri


# ---------------------------------------------------------------------------
# Phase 9B core: default mode emits a placeholder, not a fake .png.
# ---------------------------------------------------------------------------


async def test_default_face_mode_emits_placeholder_not_fake_png():
    from agents.face.handler import run as face_run

    state = _make_state(face_mode=None)
    out = await face_run(state)

    assert out.noop is True
    portrait = out.artifacts["portrait"]

    # No phantom file.
    assert portrait.local_path is None
    assert portrait.checksum_sha256 is None
    assert portrait.size_bytes is None

    # The URI cannot pretend to be a real .png.
    assert not portrait.uri.endswith(".png")
    assert "portrait.png" not in portrait.uri
    assert portrait.uri.startswith("placeholder://")

    # The placeholder is honest about itself.
    assert portrait.extra["real_face_input"] is False
    assert portrait.extra["is_placeholder"] is True
    assert portrait.extra["face_skip_reason"] == "face_provider_not_configured"
    assert portrait.extra["phase"].startswith("phase9b")


# ---------------------------------------------------------------------------
# Strict opt-in via provider_selection.
# ---------------------------------------------------------------------------


async def test_explicit_image_processor_id_makes_default_path_raise():
    from agents.face.handler import run as face_run
    from common.exceptions import StageRejection

    state = _make_state(
        face_mode=None,
        provider_selection={"image_processor_id": "future_face_cropper"},
    )
    with pytest.raises(StageRejection) as ei:
        await face_run(state)
    assert "face_provider_not_implemented" in str(ei.value)


async def test_deterministic_image_processor_id_keeps_soft_placeholder():
    """``stdlib_image_validation`` is the in-process deterministic
    validator — it doesn't request real face generation, so the
    placeholder path stays soft."""
    from agents.face.handler import run as face_run

    state = _make_state(
        face_mode=None,
        provider_selection={"image_processor_id": "stdlib_image_validation"},
    )
    out = await face_run(state)
    assert out.noop is True
    assert out.artifacts["portrait"].extra["is_placeholder"] is True


async def test_face_strict_env_makes_default_path_raise(monkeypatch):
    from agents.face.handler import run as face_run
    from common.exceptions import StageRejection

    monkeypatch.setenv("FACE_STRICT", "1")
    state = _make_state(face_mode=None)
    with pytest.raises(StageRejection) as ei:
        await face_run(state)
    assert "face_provider_not_implemented" in str(ei.value)


# ---------------------------------------------------------------------------
# Path safety / unsafe image input.
# ---------------------------------------------------------------------------


async def test_unsafe_image_path_rejected(tmp_path: Path):
    """The schema validator rejects path-traversal at construction
    time, so the handler never sees an unsafe path. Phase 9B keeps
    this defence-in-depth wired through ImageRef."""
    from common.schemas import ImageRef

    with pytest.raises(ValueError):
        ImageRef(
            type="local_path",
            path="../../etc/passwd",
            mime_type="image/png",
            consent_confirmed=True,
            synthetic_person_confirmed=True,
        )


async def test_provided_image_consent_required(tmp_path: Path, monkeypatch):
    """ImageRef refuses ``consent_confirmed=False`` at the schema level."""
    from common.schemas import ImageRef

    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(tmp_path))
    img_path = tmp_path / "synthetic.png"
    img_path.write_bytes(_make_min_png_bytes(256, 256))
    with pytest.raises(ValueError):
        ImageRef(
            type="local_path",
            path=str(img_path),
            mime_type="image/png",
            consent_confirmed=False,
            synthetic_person_confirmed=True,
        )


# ---------------------------------------------------------------------------
# Module load isolation — no heavy image / torch / onnx imports.
# ---------------------------------------------------------------------------


def test_module_load_does_not_pull_image_or_torch():
    # Drop the cached modules to force a re-import.
    for k in [k for k in list(sys.modules) if k.startswith("agents.face")]:
        sys.modules.pop(k, None)
    forbidden = {"PIL", "cv2", "torch", "onnxruntime", "diffusers"}
    before = {n for n in forbidden if n in sys.modules}

    import agents.face.handler  # noqa: F401

    after = {n for n in forbidden if n in sys.modules}
    # We only fail if our import itself dragged something in.
    leaked = after - before
    assert not leaked, f"face handler import leaked heavy deps: {leaked}"


_ = pytest  # placate lint
