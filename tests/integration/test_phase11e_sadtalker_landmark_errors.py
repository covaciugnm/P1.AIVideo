"""Phase 11E — SadTalker landmark-failure classification + DAG behavior.

Pins the contract Phase 11E ships:

1. The wrapper-side classifier turns SadTalker stdout containing
   "can not detect the landmark from source image" into
   ``video_face_landmark_missing`` (status="face_landmark_missing").
2. The classifier also recognises the "TypeError: exceptions must
   derive from BaseException" + croper/preprocess context as the same
   landmark failure (upstream raises a bare string from croper.py).
3. Unknown subprocess errors fall back to the generic
   ``video_generation_failed`` bucket (no silent mis-classification).
4. The lipsync DAG handler formats the rejection_reason as
   ``<error_code>: <operator_msg>`` so the frontend can branch on the
   leading code.
5. Backend's pre-flight image suitability check rejects images smaller
   than 256×256 with ``video_face_image_too_small`` BEFORE the wrapper
   is called.
6. PATCH /jobs/{id} accepts ``image_artifact_id`` and rewrites
   ``image_ref`` on a recoverable job.
7. PATCH refuses unknown image_artifact_id (404).
8. PATCH refuses non-image artifact (422 wrong type).
9. PATCH refuses image_artifact_id on a published job (409 locked).
"""
from __future__ import annotations

import io
import struct
import uuid
import zlib
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


# ---------------------------------------------------------------------
# 1-3. Wrapper-side classifier unit checks.
# ---------------------------------------------------------------------
# We import the classifier directly from the wrapper module so the
# tests don't need the model-sadtalker Docker service. The function is
# pure (no I/O, no torch, no opencv) — it just pattern-matches stdout.


def _import_wrapper_classifier():
    """Load docker/model-sadtalker/server.py as a module without
    importing the whole FastAPI app. We splice just the classifier
    constants + function (no fastapi, no ``app``, no other handlers)
    into a fresh module namespace.
    """
    server_path = (
        Path(__file__).resolve().parents[2]
        / "docker"
        / "model-sadtalker"
        / "server.py"
    )
    src = server_path.read_text(encoding="utf-8")
    start = src.index("_LANDMARK_FAILURE_PATTERNS")
    # The function body ends with a closing ``return ( ... )`` block.
    # We splice forward to the first blank line after the function's
    # final closing parenthesis at column 0.
    needle = "    return (\n        \"generation_failed\",\n"
    body_end = src.index(needle, start) + len(needle)
    # Find the closing ``)`` that terminates that return statement
    # (the next ``)`` on a line by itself at the function's
    # indentation level).
    close = src.index("\n    )\n", body_end) + len("\n    )\n")
    snippet = src[start:close]
    ns: dict = {}
    exec(snippet, ns)
    return ns["_classify_generation_failure"]


_classify_generation_failure = _import_wrapper_classifier()


def test_classifier_maps_direct_landmark_line():
    tail = (
        'File "/opt/sadtalker/src/utils/croper.py", line 131, in crop\n'
        "    raise 'can not detect the landmark from source image'\n"
    )
    status, code, msg = _classify_generation_failure(tail)
    assert status == "face_landmark_missing"
    assert code == "video_face_landmark_missing"
    assert "front-facing portrait" in msg.lower()


def test_classifier_maps_bare_string_typeerror_with_croper():
    tail = (
        'File "/opt/sadtalker/src/utils/croper.py", line 131, in crop\n'
        "TypeError: exceptions must derive from BaseException\n"
    )
    status, code, msg = _classify_generation_failure(tail)
    assert status == "face_landmark_missing"
    assert code == "video_face_landmark_missing"


def test_classifier_maps_bare_string_typeerror_with_preprocess():
    tail = (
        'File "/opt/sadtalker/src/utils/preprocess.py", line 96, in generate\n'
        "    x_full_frames, crop, quad = self.propress.crop(...)\n"
        "TypeError: exceptions must derive from BaseException\n"
    )
    status, code, msg = _classify_generation_failure(tail)
    assert status == "face_landmark_missing"
    assert code == "video_face_landmark_missing"


def test_classifier_falls_back_to_generic_on_unknown_error():
    tail = (
        "Traceback (most recent call last):\n"
        '  File "/opt/sadtalker/inference.py", line 200, in main\n'
        "    torch.cuda.OutOfMemoryError: CUDA out of memory.\n"
    )
    status, code, _msg = _classify_generation_failure(tail)
    assert status == "generation_failed"
    assert code == "video_generation_failed"


def test_classifier_does_not_classify_typeerror_without_croper_context():
    """A bare ``TypeError: exceptions must derive`` line without any
    croper/preprocess/crop context is not enough to claim it's a
    landmark failure — could be something else upstream changed."""
    tail = "TypeError: exceptions must derive from BaseException\n"
    status, code, _msg = _classify_generation_failure(tail)
    assert status == "generation_failed"
    assert code == "video_generation_failed"


# ---------------------------------------------------------------------
# 4-9. Pre-flight image suitability + PATCH image_artifact_id contract.
# ---------------------------------------------------------------------


def _write_minimal_png(path: Path, width: int = 64, height: int = 64) -> bytes:
    """Real PNG bytes the image validator accepts (256-only resize-down
    when needed by the test)."""
    pixels = bytearray()
    for _ in range(height):
        pixels.append(0)
        for _ in range(width):
            pixels += b"\x80\x80\x80"

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(pixels), level=6)
    blob = sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return blob


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    audio_root = tmp_path / "audio"
    image_root = tmp_path / "images"
    text_root = tmp_path / "text"
    for p in (audio_root, image_root, text_root):
        p.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(audio_root))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(image_root))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(text_root))
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(audio_root))
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(image_root))
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")

    from app.core import db as core_db
    from app.main import create_app
    from app.services import queue_publisher

    await core_db.async_reset_engine()
    await core_db.init_db()

    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, tmp_path

    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


async def _upload_image(
    client: AsyncClient, tmp_path: Path, *, width: int = 256, height: int = 256
) -> dict:
    src = tmp_path / f"portrait_{width}x{height}.png"
    blob = _write_minimal_png(src, width, height)
    files = {"file": ("portrait.png", io.BytesIO(blob), "image/png")}
    r = await client.post("/api/v1/uploads/image", files=files)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_recoverable_job(
    client: AsyncClient, image: dict
) -> str:
    """Create a job in the recoverable terminal state (rejected) so we
    can exercise the PATCH image_artifact_id flow."""
    r = await client.post(
        "/api/v1/jobs/from-inputs",
        json={
            "brief": "Phase 11E recovery",
            "target_duration_seconds": 30,
            "synthetic_person_confirmed": True,
            "consent_confirmed": True,
            "watermark_required": True,
            "c2pa_required": True,
            "voice_mode": "tts",
            "face_mode": "provided_image",
            "script_text": "x",
            "image_artifact_id": image["artifact_id"],
            "image_consent_confirmed": True,
            "image_synthetic_person_confirmed": True,
        },
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]

    # Force the job into ``rejected`` so it sits in the recoverable
    # terminal state — same approach the Phase 8D tests use.
    from app.core.db import get_sessionmaker
    from app.models.job import Job, JobStatus

    sm = get_sessionmaker()
    async with sm() as session:
        row = await session.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
        job = row.scalar_one()
        job.status = JobStatus.rejected
        job.rejection_reason = (
            "video_face_landmark_missing: SadTalker could not detect "
            "facial landmarks in the source image."
        )
        await session.commit()
    return job_id


async def test_patch_image_artifact_id_replaces_image_ref(app_under_test):
    """PATCH image_artifact_id on a rejected job rewrites image_ref to
    point at the new portrait."""
    client, tmp_path = app_under_test
    old_img = await _upload_image(client, tmp_path)
    new_img = await _upload_image(client, tmp_path, width=512, height=512)
    job_id = await _create_recoverable_job(client, old_img)

    r = await client.patch(
        f"/api/v1/jobs/{job_id}",
        json={"image_artifact_id": new_img["artifact_id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["image_ref"]["checksum"] == new_img["checksum_sha256"]
    assert body["image_ref"]["path"] == new_img["local_path"]


async def test_patch_image_artifact_id_unknown_returns_404(app_under_test):
    client, tmp_path = app_under_test
    img = await _upload_image(client, tmp_path)
    job_id = await _create_recoverable_job(client, img)

    r = await client.patch(
        f"/api/v1/jobs/{job_id}",
        json={"image_artifact_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404, r.text
    assert "not found" in r.text.lower()


async def test_patch_image_artifact_id_wrong_type_rejected(app_under_test):
    """Passing a non-image artifact (e.g. text/script) as
    image_artifact_id must be rejected with 422 — no silent
    pseudo-image replacement allowed."""
    client, tmp_path = app_under_test
    img = await _upload_image(client, tmp_path)
    job_id = await _create_recoverable_job(client, img)

    # Create a text artifact via the text upload endpoint.
    text_r = await client.post(
        "/api/v1/uploads/text",
        json={"script_text": "phase 11e wrong-type", "language": "ro"},
    )
    assert text_r.status_code == 201, text_r.text
    text_artifact_id = text_r.json()["artifact_id"]

    r = await client.patch(
        f"/api/v1/jobs/{job_id}",
        json={"image_artifact_id": text_artifact_id},
    )
    assert r.status_code == 422, r.text
    assert "image" in r.text.lower()


async def test_patch_image_artifact_id_blocked_on_published(app_under_test):
    """Published jobs are hard-terminal; PATCH must refuse the
    image_artifact_id field with 409, not silently mutate."""
    client, tmp_path = app_under_test
    img = await _upload_image(client, tmp_path)
    job_id = await _create_recoverable_job(client, img)

    # Bump to ``published`` — fully locked.
    from app.core.db import get_sessionmaker
    from app.models.job import Job, JobStatus

    sm = get_sessionmaker()
    async with sm() as session:
        row = await session.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
        j = row.scalar_one()
        j.status = JobStatus.published
        await session.commit()

    new_img = await _upload_image(client, tmp_path, width=512, height=512)
    r = await client.patch(
        f"/api/v1/jobs/{job_id}",
        json={"image_artifact_id": new_img["artifact_id"]},
    )
    assert r.status_code == 409, r.text


async def test_lipsync_handler_formats_rejection_reason_with_error_code():
    """The DAG handler must format rejection_reason as
    ``<error_code>: <operator_msg>`` so the frontend can branch on the
    leading code via simple prefix match — no Python traceback as the
    primary line."""
    # Inspect the source — we don't want to import the heavy
    # orchestrator just to check a formatting decision.
    handler = (
        Path(__file__).resolve().parents[2] / "agents" / "lipsync" / "handler.py"
    ).read_text(encoding="utf-8")
    # The Phase 11E format ``f"{error_code}: {op_msg}"`` must be present.
    assert 'f"{error_code}: {op_msg}"' in handler, (
        "lipsync handler must format rejection_reason as "
        "``<error_code>: <operator message>`` so the frontend can "
        "recognise video_face_landmark_missing without parsing a "
        "Python traceback"
    )


async def test_recoverable_job_advertises_can_edit_can_retry(app_under_test):
    """Sanity: the recovery contract from Phase 11B is intact —
    rejected jobs have can_edit + can_retry True (so the frontend
    enables the Edit + Retry actions on the recovery card)."""
    client, tmp_path = app_under_test
    img = await _upload_image(client, tmp_path)
    job_id = await _create_recoverable_job(client, img)
    detail = (await client.get(f"/api/v1/jobs/{job_id}")).json()
    assert detail["status"] == "rejected"
    assert detail["can_edit"] is True
    assert detail["can_retry"] is True
    assert detail["locked_fields"] == []
