"""Phase 3C integration tests — voice mode routing + provided-audio contract.

Covers, end-to-end through the API:

- ``voice_mode="tts"`` requires ``script_text`` (422 without it).
- ``voice_mode="tts"`` defaults ``tts_backend`` to ``"piper"``.
- ``voice_mode="provided_audio"`` requires ``audio_ref`` (422 without it).
- ``audio_ref`` is rejected with 422 if the path:
  - lives outside the configured ``PROVIDED_AUDIO_ALLOWED_ROOTS``;
  - contains a ``..`` traversal segment;
  - has a non-``.wav`` extension or a non-``audio/wav`` MIME type;
  - is missing ``consent_confirmed`` or ``synthetic_or_owned_voice``.
- A valid ``provided_audio`` request is accepted, the full DAG reaches
  ``published``, the voice stage emits an ``ArtifactRef`` whose URI is a
  ``file://`` pointer at the operator-supplied file (NOT a stub URI),
  and the ``policy_gate`` compliance row records
  ``extra={"voice_source": "provided_audio"}``.
- No binary audio enters Redis or Postgres — every artifact value remains
  a dict carrying just metadata + URI.
- Importing the new voice handler does NOT transitively pull in any heavy
  ML / audio library (verified in a fresh subprocess).

Scope reminders (Phase 3C is narrow):
- No SadTalker / SDXL / face generation / real lip-sync changes.
- No torch / diffusers / transformers added.
- No voice cloning enabled. The schema refuses any
  ``synthetic_or_owned_voice=False`` request.
- The Piper provider's lazy-import path (Phase 3B) is unchanged — Phase 3C
  does NOT wire that provider into the DAG handler.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import wave

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    """Bring up a clean app with PROVIDED_AUDIO_ALLOWED_ROOTS pointing at
    a writable tmp dir so happy-path tests have somewhere safe to drop a
    fake .wav file."""
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path))

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


def _provided_audio_payload(path: Path) -> dict:
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
            "path": str(path),
            "mime_type": "audio/wav",
            "duration_seconds": 4.2,
            "checksum": "deadbeef" * 8,
            "consent_confirmed": True,
            "synthetic_or_owned_voice": True,
        },
    }


def _runner_config():
    from agents.orchestrator.dag import DagRunnerConfig

    return DagRunnerConfig(
        signing_key="phase3c-test-key-not-for-prod",
        allowed_lipsync_backend="sadtalker",
        token_ttl_seconds=3600,
    )


def _write_real_wav(
    path: Path,
    *,
    duration_sec: float = 0.5,
    sample_rate: int = 22050,
    channels: int = 1,
) -> None:
    """Write a real (silent) PCM WAV that ``wave`` and Phase 3D's audio
    validator will both happily parse."""
    n_frames = int(duration_sec * sample_rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n_frames * channels)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


async def test_tts_mode_requires_script_text(app_under_test):
    client, _, _ = app_under_test
    payload = _tts_payload()
    del payload["script_text"]
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert any("script_text" in str(err) for err in body["detail"])


async def test_tts_mode_defaults_to_piper(app_under_test):
    client, _, _ = app_under_test
    payload = _tts_payload()
    payload.pop("tts_backend", None)
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["voice_mode"] == "tts"
    assert body["tts_backend"] == "piper"


async def test_provided_audio_mode_requires_audio_ref(app_under_test):
    client, _, _ = app_under_test
    payload = {
        "brief": "Bedtime tips.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "voice_mode": "provided_audio",
    }
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422
    assert any("audio_ref" in str(err) for err in r.json()["detail"])


async def test_provided_audio_rejects_path_outside_allowed_roots(app_under_test):
    client, _, _ = app_under_test
    payload = _provided_audio_payload(Path("/etc/passwd").with_suffix(".wav"))
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422
    assert any("allowed roots" in str(err) for err in r.json()["detail"])


async def test_provided_audio_rejects_path_traversal(app_under_test):
    client, _, tmp_path = app_under_test
    # Even though the path starts inside the allowed root, the literal `..`
    # component must be rejected before any normalization happens.
    payload = _provided_audio_payload(Path(f"{tmp_path}/../sneaky.wav"))
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422
    assert any("traversal" in str(err) for err in r.json()["detail"])


async def test_provided_audio_rejects_non_wav_extension(app_under_test):
    client, _, tmp_path = app_under_test
    payload = _provided_audio_payload(tmp_path / "narration.mp3")
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422
    assert any(".wav" in str(err) for err in r.json()["detail"])


async def test_provided_audio_rejects_non_wav_mime(app_under_test):
    client, _, tmp_path = app_under_test
    payload = _provided_audio_payload(tmp_path / "narration.wav")
    payload["audio_ref"]["mime_type"] = "audio/mpeg"
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422


async def test_provided_audio_rejects_missing_consent(app_under_test):
    client, _, tmp_path = app_under_test
    payload = _provided_audio_payload(tmp_path / "narration.wav")
    payload["audio_ref"]["consent_confirmed"] = False
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422
    assert any("consent_confirmed" in str(err) for err in r.json()["detail"])


async def test_provided_audio_rejects_missing_synthetic_or_owned(app_under_test):
    client, _, tmp_path = app_under_test
    payload = _provided_audio_payload(tmp_path / "narration.wav")
    payload["audio_ref"]["synthetic_or_owned_voice"] = False
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422
    assert any(
        "synthetic_or_owned_voice" in str(err) for err in r.json()["detail"]
    )


async def test_provided_audio_accepts_valid_metadata(app_under_test):
    client, _, tmp_path = app_under_test
    # Operator places a real (even if empty) file in the allowed root.
    audio_path = tmp_path / "narration.wav"
    audio_path.write_bytes(b"RIFF" + b"\x00" * 36)  # not a valid WAV; bytes irrelevant
    payload = _provided_audio_payload(audio_path)
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["voice_mode"] == "provided_audio"
    assert body["audio_ref"] is not None
    assert body["audio_ref"]["path"] == str(audio_path)


# ---------------------------------------------------------------------------
# End-to-end DAG: provided audio reaches `published` and emits a file:// URI
# ---------------------------------------------------------------------------


async def test_provided_audio_dag_publishes_with_file_uri(app_under_test):
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.compliance import ComplianceEvent
    from app.models.stage_run import StageRun

    client, _, tmp_path = app_under_test
    audio_path = tmp_path / "narration.wav"
    # Phase 3D's voice handler now inspects the WAV header — write a real
    # (silent) PCM WAV rather than a fake RIFF prefix.
    _write_real_wav(audio_path)
    r = await client.post("/jobs", json=_provided_audio_payload(audio_path))
    assert r.status_code == 201
    job_id = uuid.UUID(r.json()["id"])

    await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)

    # Final status must be published.
    fetched = (await client.get(f"/jobs/{job_id}")).json()
    assert fetched["status"] == "published"

    sm = get_sessionmaker()

    # Voice stage_run must point at the operator's file via file:// — NOT a
    # stub s3:// URI like the tts no-op produces.
    async with sm() as session:
        result = await session.execute(
            select(StageRun).where(
                StageRun.job_id == job_id, StageRun.stage == "voice"
            )
        )
        voice_run = result.scalar_one()
    narration = voice_run.artifacts["narration"]
    assert narration["uri"].startswith("file://")
    assert narration["uri"].endswith(audio_path.name)
    assert narration["extra"]["source"] == "provided_audio"
    assert narration["extra"]["mime_type"] == "audio/wav"

    # No binary audio bytes ever appear in the row — only metadata fields.
    serialized = json.dumps(voice_run.artifacts)
    assert "RIFF" not in serialized
    assert "\\u0000" not in serialized  # no embedded null bytes from the file

    # The policy_gate compliance row records the voice source.
    async with sm() as session:
        result = await session.execute(
            select(ComplianceEvent).where(
                ComplianceEvent.job_id == job_id,
                ComplianceEvent.gate == "policy_gate",
            )
        )
        event = result.scalar_one()
    assert event.extra.get("voice_source") == "provided_audio"


async def test_tts_dag_records_tts_voice_source(app_under_test):
    """The policy_gate compliance row for a tts job records voice_source='tts'."""
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.compliance import ComplianceEvent

    client, _, _ = app_under_test
    r = await client.post("/jobs", json=_tts_payload())
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
    assert event.extra.get("voice_source") == "tts"


# ---------------------------------------------------------------------------
# No heavy imports
# ---------------------------------------------------------------------------


def test_voice_handler_module_does_not_import_heavy_libs():
    """Importing the updated voice handler must not pull in piper / torch /
    librosa / pydub / soundfile / numpy / etc."""
    root = Path(__file__).resolve().parents[2]
    code = (
        "import sys\n"
        "from agents.voice.handler import run\n"
        "from common.path_safety import validate_local_audio_path\n"
        "from common.schemas import AudioRef\n"
        "forbidden = ['piper', 'torch', 'torchvision', 'torchaudio',\n"
        "             'transformers', 'diffusers', 'librosa', 'pydub',\n"
        "             'soundfile', 'numpy']\n"
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
