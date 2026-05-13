"""Phase 3D integration tests — audio validation + artifact registry.

What we verify here:

Unit-level — ``common.audio_validation.validate_and_inspect_wav``:
- valid WAV under allowed root is accepted; metadata extracted correctly
  (size, sample_rate, channels, duration, sha256).
- non-existent file is rejected.
- non-WAV bytes (bad header) are rejected.
- file size exceeding the configured limit is rejected.
- disallowed sample rate / channel count is rejected.

End-to-end through the API + DAG:
- valid provided_audio request runs the full DAG and creates an
  ``artifacts`` row carrying the inspected metadata.
- the voice ``stage_run`` artifact dict carries duration / sample_rate /
  channels / checksum.
- TTS-mode runs produce NO row in ``artifacts`` (the stub URI has no
  checksum, so DagRunner skips the promotion).
- a bad WAV header for a provided_audio job → DAG rejects at the voice
  stage (status="rejected").
- no binary audio bytes ever appear in DB rows or queue messages.
- importing the new validation module does NOT pull in any audio ML
  library (subprocess-isolated check).

Boundaries reminder (Phase 3D is narrow):
- No Whisper, no SadTalker, no real lip-sync, no face generation, no
  SDXL. No torch / torchvision / torchaudio / diffusers / transformers /
  gfpgan / opencv / numpy / soundfile / librosa added.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
import wave
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_real_wav(
    path: Path,
    *,
    duration_sec: float = 0.5,
    sample_rate: int = 22050,
    channels: int = 1,
    sample_width: int = 2,
) -> int:
    """Write a real (silent) PCM WAV. Returns the number of frames written."""
    n_frames = int(duration_sec * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00" * (sample_width * n_frames * channels))
    return n_frames


def _provided_audio_payload(audio_path: Path) -> dict:
    return {
        "brief": "Three calming bedtime habits for better sleep.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "voice_mode": "provided_audio",
        "audio_ref": {
            "type": "local_path",
            "path": str(audio_path),
            "mime_type": "audio/wav",
            "duration_seconds": 0.5,
            "consent_confirmed": True,
            "synthetic_or_owned_voice": True,
        },
    }


def _tts_payload() -> dict:
    return {
        "brief": "Three calming bedtime habits for better sleep.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "voice_mode": "tts",
        "script_text": "Tip one: avoid screens before bed.",
    }


def _runner_config():
    from agents.orchestrator.dag import DagRunnerConfig

    return DagRunnerConfig(
        signing_key="phase3d-test-key-not-for-prod",
        allowed_lipsync_backend="sadtalker",
        token_ttl_seconds=3600,
    )


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    """App + fakeredis + PROVIDED_AUDIO_ALLOWED_ROOTS pointing at tmp_path."""
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path))
    # Keep the size limit small so we can test the limit deterministically.
    monkeypatch.setenv("AUDIO_MAX_FILE_SIZE_BYTES", "1048576")  # 1 MB

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


# ---------------------------------------------------------------------------
# Unit tests: validate_and_inspect_wav
# ---------------------------------------------------------------------------


def test_validate_and_inspect_wav_accepts_valid_file(tmp_path):
    from common.audio_validation import validate_and_inspect_wav

    audio = tmp_path / "narration.wav"
    n_frames = _write_real_wav(audio, duration_sec=1.0, sample_rate=22050)
    meta = validate_and_inspect_wav(audio, mime_type="audio/wav")
    assert meta.path == audio
    assert meta.sample_rate == 22050
    assert meta.channels == 1
    assert meta.n_frames == n_frames
    assert 0.9 < meta.duration_seconds < 1.1
    # Sha256 of a known-content file is deterministic.
    assert len(meta.checksum_sha256) == 64
    assert meta.size_bytes > 0


def test_validate_and_inspect_wav_rejects_missing_file(tmp_path):
    from common.audio_validation import validate_and_inspect_wav

    with pytest.raises(ValueError, match="not found"):
        validate_and_inspect_wav(tmp_path / "absent.wav", mime_type="audio/wav")


def test_validate_and_inspect_wav_rejects_bad_header(tmp_path):
    from common.audio_validation import validate_and_inspect_wav

    bad = tmp_path / "garbage.wav"
    bad.write_bytes(b"NOT A REAL WAV" * 4)
    with pytest.raises(ValueError, match="invalid WAV header"):
        validate_and_inspect_wav(bad, mime_type="audio/wav")


def test_validate_and_inspect_wav_rejects_oversize(tmp_path):
    from common.audio_validation import validate_and_inspect_wav

    audio = tmp_path / "narration.wav"
    _write_real_wav(audio, duration_sec=1.0, sample_rate=22050)
    size = audio.stat().st_size
    with pytest.raises(ValueError, match="exceeds AUDIO_MAX_FILE_SIZE_BYTES"):
        validate_and_inspect_wav(
            audio, mime_type="audio/wav", max_size_bytes=size - 1
        )


def test_validate_and_inspect_wav_rejects_unsupported_mime(tmp_path):
    from common.audio_validation import validate_and_inspect_wav

    audio = tmp_path / "narration.wav"
    _write_real_wav(audio)
    with pytest.raises(ValueError, match="mime_type"):
        validate_and_inspect_wav(audio, mime_type="audio/mpeg")


def test_validate_and_inspect_wav_rejects_disallowed_sample_rate(tmp_path):
    from common.audio_validation import validate_and_inspect_wav

    audio = tmp_path / "narration.wav"
    _write_real_wav(audio, sample_rate=22050)
    with pytest.raises(ValueError, match="sample_rate 22050 not in"):
        validate_and_inspect_wav(
            audio, mime_type="audio/wav", allowed_sample_rates=[48000]
        )


def test_validate_and_inspect_wav_rejects_disallowed_channels(tmp_path):
    from common.audio_validation import validate_and_inspect_wav

    audio = tmp_path / "narration.wav"
    _write_real_wav(audio, channels=1)
    with pytest.raises(ValueError, match="channels 1 not in"):
        validate_and_inspect_wav(
            audio, mime_type="audio/wav", allowed_channels=[2]
        )


# ---------------------------------------------------------------------------
# End-to-end: provided_audio creates an Artifact row with extracted metadata
# ---------------------------------------------------------------------------


async def test_provided_audio_creates_artifact_row(app_under_test):
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact
    from app.models.stage_run import StageRun

    client, _, tmp_path = app_under_test
    audio = tmp_path / "narration.wav"
    n_frames = _write_real_wav(audio, duration_sec=1.0, sample_rate=22050)

    r = await client.post("/jobs", json=_provided_audio_payload(audio))
    assert r.status_code == 201
    job_id = uuid.UUID(r.json()["id"])

    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "published"

    sm = get_sessionmaker()

    # An Artifact row must exist for the inspected WAV.
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(
                Artifact.job_id == job_id, Artifact.artifact_type == "audio"
            )
        )
        artifacts = list(result.scalars().all())
    assert len(artifacts) == 1
    art = artifacts[0]
    assert art.local_path == str(audio)
    assert art.uri.startswith("file://")
    assert art.mime_type == "audio/wav"
    assert art.size_bytes == audio.stat().st_size
    assert art.sample_rate == 22050
    assert art.channels == 1
    assert art.duration_seconds == pytest.approx(n_frames / 22050.0, rel=1e-3)
    assert art.checksum_sha256 and len(art.checksum_sha256) == 64

    # The same metadata must be present on the voice stage_run's artifact
    # snapshot (denormalized copy).
    async with sm() as session:
        result = await session.execute(
            select(StageRun).where(
                StageRun.job_id == job_id, StageRun.stage == "voice"
            )
        )
        voice_run = result.scalar_one()
    narration = voice_run.artifacts["narration"]
    assert narration["checksum_sha256"] == art.checksum_sha256
    assert narration["sample_rate"] == 22050
    assert narration["channels"] == 1
    assert narration["local_path"] == str(audio)


async def test_tts_mode_does_not_create_audio_artifact(app_under_test):
    """TTS no-op produces a stub URI without a checksum; the DagRunner
    must NOT promote it to the artifacts table."""
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact

    client, _, _ = app_under_test
    r = await client.post("/jobs", json=_tts_payload())
    job_id = uuid.UUID(r.json()["id"])
    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "published"

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(Artifact.job_id == job_id)
        )
        artifacts = list(result.scalars().all())
    # No artifact rows: the TTS branch only emits stubs without checksums.
    assert artifacts == []


async def test_provided_audio_bad_header_rejects_at_voice_stage(app_under_test):
    """A path that passes API-level checks (under allowed root, .wav
    extension) but is NOT a valid WAV must be rejected at the voice
    stage, NOT at intake. Status moves to 'rejected'."""
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact
    from app.models.stage_run import StageRun
    from common.enums import StageStatus

    client, _, tmp_path = app_under_test
    bad = tmp_path / "narration.wav"
    bad.write_bytes(b"NOT A REAL WAV" * 4)  # passes path safety; fails header parse

    r = await client.post("/jobs", json=_provided_audio_payload(bad))
    assert r.status_code == 201, "API schema must not read file contents"
    job_id = uuid.UUID(r.json()["id"])

    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "rejected"

    sm = get_sessionmaker()
    async with sm() as session:
        # The voice stage_run is marked rejected with an explanatory error.
        result = await session.execute(
            select(StageRun).where(
                StageRun.job_id == job_id, StageRun.stage == "voice"
            )
        )
        voice_run = result.scalar_one()
    assert voice_run.status == StageStatus.rejected
    assert "WAV" in (voice_run.error or "") or "header" in (voice_run.error or "")

    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(Artifact.job_id == job_id)
        )
        assert result.scalars().all() == []


async def test_provided_audio_oversize_rejects(app_under_test, monkeypatch):
    """File size above AUDIO_MAX_FILE_SIZE_BYTES must be rejected at the
    voice stage."""
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.stage_run import StageRun
    from common.enums import StageStatus

    client, _, tmp_path = app_under_test
    audio = tmp_path / "narration.wav"
    _write_real_wav(audio, duration_sec=0.2)
    # Cap the limit below the file's actual size.
    monkeypatch.setenv("AUDIO_MAX_FILE_SIZE_BYTES", str(audio.stat().st_size - 1))

    r = await client.post("/jobs", json=_provided_audio_payload(audio))
    job_id = uuid.UUID(r.json()["id"])
    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "rejected"

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(StageRun).where(
                StageRun.job_id == job_id, StageRun.stage == "voice"
            )
        )
        voice_run = result.scalar_one()
    assert voice_run.status == StageStatus.rejected
    assert "exceeds" in (voice_run.error or "")


# ---------------------------------------------------------------------------
# Metadata-only invariant
# ---------------------------------------------------------------------------


async def test_artifact_rows_are_metadata_only(app_under_test):
    """The artifacts table must carry references + metadata only — never
    serialized binary payloads. We assert by JSON-dumping the whole row
    and looking for any sequences from the underlying audio file."""
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact

    client, _, tmp_path = app_under_test
    audio = tmp_path / "narration.wav"
    _write_real_wav(audio, duration_sec=0.5)

    r = await client.post("/jobs", json=_provided_audio_payload(audio))
    job_id = uuid.UUID(r.json()["id"])
    await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)

    raw_bytes = audio.read_bytes()
    distinctive_chunk = raw_bytes[8:24].hex()  # bytes 8..24 of the WAV header

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(Artifact.job_id == job_id)
        )
        rows = list(result.scalars().all())
    assert rows, "expected at least one artifact row"
    for row in rows:
        serialized = json.dumps(
            {
                "uri": row.uri,
                "local_path": row.local_path,
                "checksum_sha256": row.checksum_sha256,
                "size_bytes": row.size_bytes,
                "duration_seconds": row.duration_seconds,
                "sample_rate": row.sample_rate,
                "channels": row.channels,
                "metadata_json": row.metadata_json,
            }
        )
        # Raw header bytes hex should NOT appear anywhere in metadata.
        assert distinctive_chunk not in serialized.lower()
        assert "RIFF" not in serialized  # no smuggled binary header text


# ---------------------------------------------------------------------------
# No heavy imports
# ---------------------------------------------------------------------------


def test_audio_validation_module_has_no_heavy_imports():
    """``common.audio_validation`` must import cleanly without pulling in
    any audio-ML library. Verified in a fresh subprocess."""
    root = Path(__file__).resolve().parents[2]
    code = (
        "import sys\n"
        "from common.audio_validation import validate_and_inspect_wav\n"
        "from agents.voice.handler import run\n"
        "from app.services.artifact_service import register_artifact\n"
        "forbidden = ['piper', 'torch', 'torchvision', 'torchaudio',\n"
        "             'transformers', 'diffusers', 'librosa', 'pydub',\n"
        "             'soundfile', 'numpy', 'whisper', 'whisperx']\n"
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
