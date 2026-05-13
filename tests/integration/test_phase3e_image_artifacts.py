"""Phase 3E integration tests — image input validation + face artifact registry.

What we verify:

Unit-level (``common.image_validation.validate_and_inspect_image``):
- Valid PNG / JPEG / WebP (VP8X) headers are accepted; width / height /
  size / sha256 extracted.
- Missing file is rejected.
- Bad header (file claims one mime_type but bytes don't match) is rejected.
- Oversize is rejected.
- min_width / min_height enforcement.

End-to-end through the API + DAG:
- ``face_mode="provided_image"`` requires ``image_ref`` (422 without it).
- ``image_ref`` schema rejects: missing consent, missing
  synthetic_person_confirmed, unsupported mime_type, unsupported extension,
  paths outside allowed roots, ``..`` traversal.
- A valid PNG (or JPEG / WebP) under an allowed root runs the full DAG,
  the face stage emits an ``ArtifactRef`` carrying width / height / size /
  sha256, and an ``artifacts`` row is created with ``artifact_type="image"``.
- Compliance event extra records ``face_source="provided_image"`` (vs
  ``"stub"`` for jobs without ``face_mode``).
- Bad header (passes API path-safety, fails handler inspection) → DAG
  rejects at the face stage.
- Oversize → DAG rejects at the face stage.
- No binary image bytes ever appear in ``artifacts`` rows.
- Importing ``common.image_validation`` and the face handler does NOT
  pull in any image-ML library (subprocess-isolated check).

Boundaries reminder:
- No SDXL, no face generation, no celebrity / identity matching.
- No torch / Pillow / OpenCV / imageio / numpy added.
- No model weights downloaded.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


# ---------------------------------------------------------------------------
# Hand-crafted minimal image bytes (no Pillow / imageio)
# ---------------------------------------------------------------------------


def write_test_png(path: Path, *, width: int = 64, height: int = 64) -> None:
    """Write a minimal PNG-ish file whose IHDR is enough for the validator.

    The full IDAT/IEND chunks are skipped — Phase 3E's validator reads
    only the first 24 bytes (signature + IHDR) to extract dimensions.
    Tests don't decode pixels.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = (
        b"\x00\x00\x00\x0d"  # IHDR length = 13
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"  # depth=8, color=6 RGBA, compression=0, filter=0, interlace=0
        + b"\x00\x00\x00\x00"  # fake CRC (validator doesn't check)
    )
    tail = b"\x00\x00\x00\x00IEND\xae\x42\x60\x82"
    path.write_bytes(sig + ihdr + tail)


def write_test_jpeg(path: Path, *, width: int = 64, height: int = 64) -> None:
    """Write a minimal JPEG with an SOF0 segment carrying width / height."""
    path.parent.mkdir(parents=True, exist_ok=True)
    soi = b"\xff\xd8"
    # SOF0: marker + length(2) + precision(1) + H(2) + W(2) + nf(1) + 3*comp(3)
    sof0 = (
        b"\xff\xc0"
        + b"\x00\x11"  # length = 17
        + b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03"
        + b"\x01\x22\x00"
        + b"\x02\x11\x01"
        + b"\x03\x11\x01"
    )
    eoi = b"\xff\xd9"
    path.write_bytes(soi + sof0 + eoi)


def write_test_webp_vp8x(path: Path, *, width: int = 64, height: int = 64) -> None:
    """Write a minimal VP8X WebP whose canvas dims encode (width, height)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # VP8X chunk: 4-byte id + 4-byte size + 1 flag + 3 reserved + 3 w-1 + 3 h-1
    chunk_size = 10
    vp8x_chunk = (
        b"VP8X"
        + struct.pack("<I", chunk_size)
        + b"\x00"  # flags
        + b"\x00\x00\x00"  # reserved
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
    )
    # RIFF header
    file_size_field = (4 + len(vp8x_chunk)).to_bytes(4, "little")  # "WEBP" + chunks
    riff = b"RIFF" + file_size_field + b"WEBP"
    path.write_bytes(riff + vp8x_chunk)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    """App + fakeredis + image allowlist scoped to a writable tmp dir."""
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("IMAGE_MAX_FILE_SIZE_BYTES", "1048576")  # 1 MB

    from app.core import db as core_db
    from app.main import create_app
    from app.services import queue_publisher

    await core_db.async_reset_engine()
    await core_db.init_db()

    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake, tmp_path

    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


def _base_payload() -> dict:
    return {
        "brief": "Three calming bedtime habits for better sleep.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        # Phase 3C TTS requirement.
        "script_text": "Tip one: avoid screens before bed.",
    }


def _provided_image_payload(image_path: Path, *, mime_type: str = "image/png") -> dict:
    payload = _base_payload()
    payload.update(
        {
            "face_mode": "provided_image",
            "image_ref": {
                "type": "local_path",
                "path": str(image_path),
                "mime_type": mime_type,
                "consent_confirmed": True,
                "synthetic_person_confirmed": True,
            },
        }
    )
    return payload


def _runner_config():
    from agents.orchestrator.dag import DagRunnerConfig

    return DagRunnerConfig(
        signing_key="phase3e-test-key-not-for-prod",
        allowed_lipsync_backend="sadtalker",
        token_ttl_seconds=3600,
    )


# ---------------------------------------------------------------------------
# Unit tests: validate_and_inspect_image
# ---------------------------------------------------------------------------


def test_validate_image_accepts_png(tmp_path):
    from common.image_validation import validate_and_inspect_image

    p = tmp_path / "p.png"
    write_test_png(p, width=128, height=96)
    meta = validate_and_inspect_image(p, mime_type="image/png")
    assert meta.format == "png"
    assert meta.width == 128
    assert meta.height == 96
    assert meta.size_bytes > 0
    assert len(meta.checksum_sha256) == 64


def test_validate_image_accepts_jpeg(tmp_path):
    from common.image_validation import validate_and_inspect_image

    p = tmp_path / "p.jpg"
    write_test_jpeg(p, width=320, height=240)
    meta = validate_and_inspect_image(p, mime_type="image/jpeg")
    assert meta.format == "jpeg"
    assert meta.width == 320
    assert meta.height == 240


def test_validate_image_accepts_webp_vp8x(tmp_path):
    from common.image_validation import validate_and_inspect_image

    p = tmp_path / "p.webp"
    write_test_webp_vp8x(p, width=512, height=384)
    meta = validate_and_inspect_image(p, mime_type="image/webp")
    assert meta.format == "webp"
    assert meta.width == 512
    assert meta.height == 384


def test_validate_image_rejects_missing_file(tmp_path):
    from common.image_validation import validate_and_inspect_image

    with pytest.raises(ValueError, match="not found"):
        validate_and_inspect_image(tmp_path / "absent.png", mime_type="image/png")


def test_validate_image_rejects_bad_header(tmp_path):
    from common.image_validation import validate_and_inspect_image

    bad = tmp_path / "garbage.png"
    bad.write_bytes(b"NOT A REAL PNG FILE" * 10)
    with pytest.raises(ValueError, match="PNG"):
        validate_and_inspect_image(bad, mime_type="image/png")


def test_validate_image_rejects_oversize(tmp_path):
    from common.image_validation import validate_and_inspect_image

    p = tmp_path / "p.png"
    write_test_png(p)
    size = p.stat().st_size
    with pytest.raises(ValueError, match="exceeds IMAGE_MAX_FILE_SIZE_BYTES"):
        validate_and_inspect_image(
            p, mime_type="image/png", max_size_bytes=size - 1
        )


def test_validate_image_rejects_unsupported_mime(tmp_path):
    from common.image_validation import validate_and_inspect_image

    p = tmp_path / "p.png"
    write_test_png(p)
    with pytest.raises(ValueError, match="mime_type"):
        validate_and_inspect_image(p, mime_type="image/gif")


def test_validate_image_enforces_min_dimensions(tmp_path):
    from common.image_validation import validate_and_inspect_image

    p = tmp_path / "p.png"
    write_test_png(p, width=64, height=64)
    with pytest.raises(ValueError, match="below configured IMAGE_MIN_WIDTH"):
        validate_and_inspect_image(p, mime_type="image/png", min_width=128)
    with pytest.raises(ValueError, match="below configured IMAGE_MIN_HEIGHT"):
        validate_and_inspect_image(p, mime_type="image/png", min_height=128)


# ---------------------------------------------------------------------------
# Schema validation (API layer)
# ---------------------------------------------------------------------------


async def test_face_mode_provided_image_requires_image_ref(app_under_test):
    client, _, _ = app_under_test
    payload = _base_payload()
    payload["face_mode"] = "provided_image"
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422
    assert any("image_ref" in str(err) for err in r.json()["detail"])


async def test_provided_image_rejects_path_outside_allowed_roots(app_under_test):
    client, _, _ = app_under_test
    payload = _provided_image_payload(Path("/etc/passwd.png"))
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422
    assert any("allowed roots" in str(err) for err in r.json()["detail"])


async def test_provided_image_rejects_path_traversal(app_under_test):
    client, _, tmp_path = app_under_test
    payload = _provided_image_payload(Path(f"{tmp_path}/../escape.png"))
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422
    assert any("traversal" in str(err) for err in r.json()["detail"])


async def test_provided_image_rejects_unsupported_extension(app_under_test):
    client, _, tmp_path = app_under_test
    payload = _provided_image_payload(tmp_path / "portrait.gif")
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422


async def test_provided_image_rejects_unsupported_mime(app_under_test):
    client, _, tmp_path = app_under_test
    payload = _provided_image_payload(tmp_path / "portrait.png")
    payload["image_ref"]["mime_type"] = "image/gif"
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422


async def test_provided_image_rejects_missing_consent(app_under_test):
    client, _, tmp_path = app_under_test
    payload = _provided_image_payload(tmp_path / "portrait.png")
    payload["image_ref"]["consent_confirmed"] = False
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422
    assert any("consent_confirmed" in str(err) for err in r.json()["detail"])


async def test_provided_image_rejects_missing_synthetic_person_confirmed(app_under_test):
    client, _, tmp_path = app_under_test
    payload = _provided_image_payload(tmp_path / "portrait.png")
    payload["image_ref"]["synthetic_person_confirmed"] = False
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422
    assert any(
        "synthetic_person_confirmed" in str(err) for err in r.json()["detail"]
    )


async def test_provided_image_accepts_valid_metadata(app_under_test):
    """API accepts the request even before the file exists — the schema
    only checks path *safety*, not file presence (handler inspects later)."""
    client, _, tmp_path = app_under_test
    image_path = tmp_path / "portrait.png"
    write_test_png(image_path)
    r = await client.post("/jobs", json=_provided_image_payload(image_path))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["face_mode"] == "provided_image"
    assert body["image_ref"]["path"] == str(image_path)
    assert body["image_ref"]["mime_type"] == "image/png"


# ---------------------------------------------------------------------------
# End-to-end DAG: provided_image creates an Artifact row
# ---------------------------------------------------------------------------


async def test_provided_image_creates_artifact_row(app_under_test):
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact
    from app.models.compliance import ComplianceEvent
    from app.models.stage_run import StageRun

    client, _, tmp_path = app_under_test
    image_path = tmp_path / "portrait.png"
    write_test_png(image_path, width=512, height=512)

    r = await client.post("/jobs", json=_provided_image_payload(image_path))
    assert r.status_code == 201
    job_id = uuid.UUID(r.json()["id"])

    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "published"

    sm = get_sessionmaker()

    # Exactly one image artifact row, populated from the inspected file.
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(
                Artifact.job_id == job_id, Artifact.artifact_type == "image"
            )
        )
        artifacts = list(result.scalars().all())
    assert len(artifacts) == 1
    art = artifacts[0]
    assert art.local_path == str(image_path)
    assert art.uri.startswith("file://")
    assert art.mime_type == "image/png"
    assert art.size_bytes == image_path.stat().st_size
    assert art.width == 512
    assert art.height == 512
    assert art.checksum_sha256 and len(art.checksum_sha256) == 64

    # Stage-run snapshot carries the same metadata.
    async with sm() as session:
        result = await session.execute(
            select(StageRun).where(
                StageRun.job_id == job_id, StageRun.stage == "face"
            )
        )
        face_run = result.scalar_one()
    portrait = face_run.artifacts["portrait"]
    assert portrait["width"] == 512
    assert portrait["height"] == 512
    assert portrait["checksum_sha256"] == art.checksum_sha256
    assert portrait["local_path"] == str(image_path)

    # Compliance event records the face source.
    async with sm() as session:
        result = await session.execute(
            select(ComplianceEvent).where(
                ComplianceEvent.job_id == job_id,
                ComplianceEvent.gate == "policy_gate",
            )
        )
        event = result.scalar_one()
    assert event.extra.get("face_source") == "provided_image"


async def test_default_face_mode_records_stub_face_source(app_under_test):
    """Jobs without face_mode get face_source='stub' on the compliance row
    and produce no image artifact row."""
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact
    from app.models.compliance import ComplianceEvent

    client, _, _ = app_under_test
    r = await client.post("/jobs", json=_base_payload())
    job_id = uuid.UUID(r.json()["id"])
    await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(ComplianceEvent).where(
                ComplianceEvent.job_id == job_id,
                ComplianceEvent.gate == "policy_gate",
            )
        )
        event = result.scalar_one()
    assert event.extra.get("face_source") == "stub"

    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(
                Artifact.job_id == job_id, Artifact.artifact_type == "image"
            )
        )
        assert result.scalars().all() == []


async def test_provided_image_bad_header_rejects_at_face_stage(app_under_test):
    """Path-safety passes (under allowed root, .png extension) but the file
    isn't a real PNG — face stage must reject, not Publisher."""
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact
    from app.models.stage_run import StageRun
    from common.enums import StageStatus

    client, _, tmp_path = app_under_test
    bad = tmp_path / "portrait.png"
    bad.write_bytes(b"NOT A REAL PNG FILE" * 10)

    r = await client.post("/jobs", json=_provided_image_payload(bad))
    assert r.status_code == 201, "API doesn't read file contents"
    job_id = uuid.UUID(r.json()["id"])

    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "rejected"

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(StageRun).where(
                StageRun.job_id == job_id, StageRun.stage == "face"
            )
        )
        face_run = result.scalar_one()
    assert face_run.status == StageStatus.rejected
    assert "PNG" in (face_run.error or "")

    async with sm() as session:
        # No IMAGE artifact — face rejected before it could register one.
        # Phase 3G's scriptwriter that ran earlier may have produced a
        # script-type artifact; that's expected and unrelated to this test.
        result = await session.execute(
            select(Artifact).where(
                Artifact.job_id == job_id, Artifact.artifact_type == "image"
            )
        )
        assert result.scalars().all() == []


async def test_provided_image_oversize_rejects(app_under_test, monkeypatch):
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.stage_run import StageRun
    from common.enums import StageStatus

    client, _, tmp_path = app_under_test
    image = tmp_path / "portrait.png"
    write_test_png(image)
    monkeypatch.setenv("IMAGE_MAX_FILE_SIZE_BYTES", str(image.stat().st_size - 1))

    r = await client.post("/jobs", json=_provided_image_payload(image))
    job_id = uuid.UUID(r.json()["id"])
    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "rejected"

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(StageRun).where(
                StageRun.job_id == job_id, StageRun.stage == "face"
            )
        )
        face_run = result.scalar_one()
    assert face_run.status == StageStatus.rejected
    assert "exceeds" in (face_run.error or "")


# ---------------------------------------------------------------------------
# Metadata-only invariant
# ---------------------------------------------------------------------------


async def test_image_artifact_rows_are_metadata_only(app_under_test):
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact

    client, _, tmp_path = app_under_test
    image = tmp_path / "portrait.png"
    write_test_png(image, width=256, height=256)
    r = await client.post("/jobs", json=_provided_image_payload(image))
    job_id = uuid.UUID(r.json()["id"])
    await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)

    raw = image.read_bytes()
    distinctive = raw[:16].hex()

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(
                Artifact.job_id == job_id, Artifact.artifact_type == "image"
            )
        )
        rows = list(result.scalars().all())
    assert rows
    for row in rows:
        serialized = json.dumps(
            {
                "uri": row.uri,
                "local_path": row.local_path,
                "mime_type": row.mime_type,
                "checksum_sha256": row.checksum_sha256,
                "size_bytes": row.size_bytes,
                "width": row.width,
                "height": row.height,
                "metadata_json": row.metadata_json,
            }
        )
        assert distinctive not in serialized.lower()
        # Smuggled binary PNG signature should not appear:
        assert "\\x89PNG" not in serialized


# ---------------------------------------------------------------------------
# No heavy imports
# ---------------------------------------------------------------------------


def test_image_validation_has_no_heavy_imports():
    root = Path(__file__).resolve().parents[2]
    code = (
        "import sys\n"
        "from common.image_validation import validate_and_inspect_image\n"
        "from agents.face.handler import run\n"
        "forbidden = ['PIL', 'pillow', 'cv2', 'opencv', 'imageio',\n"
        "             'numpy', 'torch', 'torchvision', 'diffusers',\n"
        "             'transformers', 'sadtalker']\n"
        "loaded = [m for m in forbidden if m in sys.modules]\n"
        "import json\n"
        "print(json.dumps(loaded))\n"
    )
    env = os.environ.copy()
    pp = env.get("PYTHONPATH", "")
    extras = [str(root), str(root / "backend")]
    env["PYTHONPATH"] = os.pathsep.join(extras + ([pp] if pp else []))
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(root),
        timeout=30,
    )
    assert result.returncode == 0, (
        f"subprocess failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    loaded = json.loads(result.stdout.strip())
    assert loaded == [], f"Heavy modules transitively imported: {loaded}"
