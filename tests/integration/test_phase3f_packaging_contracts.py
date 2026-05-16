"""Phase 3F integration tests — packaging + ArtifactType enum hardening.

Verified here:

Packaging (subprocess-isolated, NO PYTHONPATH hacks):
- ``common``, ``app``, and every required ``agents.*`` subpackage import
  cleanly from a fresh interpreter that only sees the installed editable
  packages. No project-root or backend/ entries are injected into
  ``sys.path``. This proves that ``pip install -e ./common``,
  ``pip install -e ./backend[dev]``, and ``pip install -e ./agents[dev]``
  alone are sufficient to make the import graph work, in dev and in
  Docker.
- The list of importable ``agents.*`` subpackages matches the contract
  spec exactly. No additions, no removals without an explicit update
  here.

ArtifactType enum hardening:
- ``common.enums.ArtifactType`` carries the six canonical values:
  ``audio``, ``image``, ``script``, ``video``, ``metadata``, ``final_export``.
- The two Phase 3-era handlers that produce real (validated) artifacts —
  voice (provided_audio) and face (provided_image) — use the enum and
  not bare string literals.
- A round-trip job through the DAG produces ``artifacts`` rows whose
  ``artifact_type`` column equals ``ArtifactType.<name>.value`` exactly.

No-heavy-imports invariant (subprocess):
- Importing the full ``agents`` package tree (every leaf module) does NOT
  pull in any LLM / model client / inference library. Specifically we
  assert none of: openai, langchain, langchain-core, transformers,
  torch, torchvision, torchaudio, diffusers, accelerate, xformers,
  whisper, whisperx, sentencepiece.

This file documents the packaging contract; future phases that add new
agent subpackages MUST extend ``EXPECTED_AGENT_SUBPACKAGES`` below or
this test will fail loudly.
"""
from __future__ import annotations

import importlib
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
# Contract: required `agents.*` subpackages
# ---------------------------------------------------------------------------


# Every entry here must remain importable as ``import agents.<name>``
# from a clean interpreter after ``pip install -e ./agents``.
EXPECTED_AGENT_SUBPACKAGES: tuple[str, ...] = (
    "compliance_officer",
    "orchestrator",
    "scriptwriter",
    # Phase 3G: scriptwriter provider tree.
    "scriptwriter.core",
    "scriptwriter.providers",
    "scriptwriter.providers.template",
    "scriptwriter.providers.ollama",
    "scriptwriter.providers.vllm",
    "scriptwriter.providers.openai_compatible",
    "scriptwriter.providers.openai",
    "scriptwriter.providers.anthropic",
    "scriptwriter.providers.local_http",
    "voice",
    "voice.core",
    "voice.providers",
    "voice.providers.piper",
    "face",
    "editor",
    "qc",
    "publisher",
    "lipsync",
    "lipsync.core",
    "lipsync.providers",
    "lipsync.providers.sadtalker",
    "lipsync.providers.musetalk",
    "lipsync.providers.wav2lip",
)


EXPECTED_COMMON_MODULES: tuple[str, ...] = (
    "common.enums",
    "common.schemas",
    "common.exceptions",
    "common.path_safety",
    "common.audio_validation",
    "common.image_validation",
)


EXPECTED_BACKEND_MODULES: tuple[str, ...] = (
    "app.main",
    "app.core.config",
    "app.core.db",
    "app.models",
    "app.models.artifact",
    "app.models.compliance",
    "app.models.job",
    "app.models.stage_run",
    "app.services.job_service",
    "app.services.artifact_service",
    "app.services.stage_run_service",
    "app.services.queue_publisher",
    "app.api.healthz",
    "app.api.jobs",
)


def _run_clean_interpreter(code: str, *, allow_pythonpath: bool = False) -> dict:
    """Run ``code`` in a fresh interpreter with PYTHONPATH stripped.

    Returns the JSON-decoded last line of stdout. Raises ``AssertionError``
    if the subprocess exits non-zero.
    """
    env = os.environ.copy()
    if not allow_pythonpath:
        env.pop("PYTHONPATH", None)
    # Resolve to the same Python the test is running under (the venv's
    # interpreter) so the installed packages are visible.
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, (
        "subprocess failed:\n"
        f"  stdout={result.stdout!r}\n"
        f"  stderr={result.stderr!r}"
    )
    # The test code is expected to print exactly one JSON line at the end.
    last_line = result.stdout.strip().splitlines()[-1]
    return json.loads(last_line)


# ---------------------------------------------------------------------------
# Packaging: agents
# ---------------------------------------------------------------------------


def test_agents_subpackages_import_without_pythonpath():
    """Every entry in ``EXPECTED_AGENT_SUBPACKAGES`` must be importable
    in a fresh interpreter whose PYTHONPATH is empty."""
    code = (
        "import json, importlib\n"
        f"names = {list(EXPECTED_AGENT_SUBPACKAGES)!r}\n"
        "results = {}\n"
        "for name in names:\n"
        "    try:\n"
        "        m = importlib.import_module(f'agents.{name}')\n"
        "        results[name] = m.__name__\n"
        "    except Exception as exc:\n"
        "        results[name] = f'ERROR: {type(exc).__name__}: {exc}'\n"
        "print(json.dumps(results))\n"
    )
    results = _run_clean_interpreter(code)
    bad = {k: v for k, v in results.items() if v.startswith("ERROR:")}
    assert not bad, f"Some agents.* subpackages failed to import: {bad}"
    # And every name resolved to the expected module.
    for name in EXPECTED_AGENT_SUBPACKAGES:
        assert results[name] == f"agents.{name}", (
            f"agents.{name} resolved to {results[name]!r}"
        )


def test_agents_package_root_is_installed():
    """``import agents`` must resolve to the repo's agents/__init__.py."""
    code = (
        "import json, agents\n"
        "print(json.dumps({'file': agents.__file__}))\n"
    )
    out = _run_clean_interpreter(code)
    # The installed editable package's __file__ must end in agents/__init__.py.
    file_path = out["file"]
    assert file_path.endswith("/agents/__init__.py"), file_path


# ---------------------------------------------------------------------------
# Packaging: common
# ---------------------------------------------------------------------------


def test_common_modules_import_without_pythonpath():
    code = (
        "import json, importlib\n"
        f"names = {list(EXPECTED_COMMON_MODULES)!r}\n"
        "results = {}\n"
        "for name in names:\n"
        "    try:\n"
        "        m = importlib.import_module(name)\n"
        "        results[name] = m.__name__\n"
        "    except Exception as exc:\n"
        "        results[name] = f'ERROR: {type(exc).__name__}: {exc}'\n"
        "print(json.dumps(results))\n"
    )
    results = _run_clean_interpreter(code)
    bad = {k: v for k, v in results.items() if v.startswith("ERROR:")}
    assert not bad, f"Some common.* modules failed to import: {bad}"


# ---------------------------------------------------------------------------
# Packaging: backend (`app.*`)
# ---------------------------------------------------------------------------


def test_backend_modules_import_without_pythonpath():
    code = (
        "import json, importlib\n"
        f"names = {list(EXPECTED_BACKEND_MODULES)!r}\n"
        "results = {}\n"
        "for name in names:\n"
        "    try:\n"
        "        m = importlib.import_module(name)\n"
        "        results[name] = m.__name__\n"
        "    except Exception as exc:\n"
        "        results[name] = f'ERROR: {type(exc).__name__}: {exc}'\n"
        "print(json.dumps(results))\n"
    )
    results = _run_clean_interpreter(code)
    bad = {k: v for k, v in results.items() if v.startswith("ERROR:")}
    assert not bad, f"Some app.* modules failed to import: {bad}"


# ---------------------------------------------------------------------------
# No-heavy-imports across the full agents tree
# ---------------------------------------------------------------------------


def test_full_agents_import_has_no_heavy_or_llm_dependencies():
    """Importing every ``agents.*`` subpackage (every leaf module) must
    NOT transitively load any LLM client, inference framework, or audio /
    image ML library."""
    forbidden = [
        "openai",
        "anthropic",
        "langchain",
        "langchain_core",
        "langgraph",
        "transformers",
        "torch",
        "torchvision",
        "torchaudio",
        "diffusers",
        "accelerate",
        "xformers",
        "whisper",
        "whisperx",
        "sentencepiece",
        "PIL",
        "cv2",
        "imageio",
        "numpy",
        "piper",
        "librosa",
        "soundfile",
        "gfpgan",
        # Scriptwriter stubs must not import HTTP clients at module load.
        "httpx",
        "requests",
        "aiohttp",
    ]
    leaf_modules = [
        "agents.compliance_officer.policy_gate",
        "agents.compliance_officer.compliance_token",
        "agents.compliance_officer.identity_guard",
        "agents.compliance_officer.pre_lipsync_auth",
        "agents.compliance_officer.export_disclosure_validation",
        "agents.orchestrator.dag",
        "agents.orchestrator.handlers",
        "agents.orchestrator.orchestrator",
        "agents.scriptwriter.handler",
        # Phase 3G scriptwriter provider tree:
        "agents.scriptwriter.core.provider",
        "agents.scriptwriter.core.registry",
        "agents.scriptwriter.providers.template.provider",
        "agents.scriptwriter.providers.ollama.provider",
        "agents.scriptwriter.providers.vllm.provider",
        "agents.scriptwriter.providers.openai_compatible.provider",
        "agents.scriptwriter.providers.openai.provider",
        "agents.scriptwriter.providers.anthropic.provider",
        "agents.scriptwriter.providers.local_http.provider",
        "agents.voice.handler",
        "agents.voice.core.provider",
        "agents.voice.core.registry",
        "agents.voice.providers.piper.provider",
        "agents.face.handler",
        "agents.editor.handler",
        "agents.qc.handler",
        "agents.publisher.handler",
        "agents.lipsync.handler",
        "agents.lipsync.core.provider",
        "agents.lipsync.core.registry",
        "agents.lipsync.providers.sadtalker.provider",
        "agents.lipsync.providers.musetalk.provider",
        "agents.lipsync.providers.wav2lip.provider",
    ]
    code = (
        "import json, sys, importlib\n"
        f"forbidden = {forbidden!r}\n"
        f"modules = {leaf_modules!r}\n"
        "for m in modules:\n"
        "    importlib.import_module(m)\n"
        "loaded = sorted(m for m in forbidden if m in sys.modules)\n"
        "print(json.dumps(loaded))\n"
    )
    loaded = _run_clean_interpreter(code)
    assert loaded == [], (
        f"Heavy / LLM modules transitively imported by the agents tree: {loaded}"
    )


# ---------------------------------------------------------------------------
# ArtifactType enum contract
# ---------------------------------------------------------------------------


def test_artifact_type_enum_has_expected_values():
    from common.enums import ArtifactType

    actual = sorted(member.value for member in ArtifactType)
    expected = sorted(
        [
            "audio",
            "image",
            "script",
            "edit_plan",  # added in Phase 3H
            "video",
            "metadata",
            "final_export",
            "subtitle",  # added in Phase 11A
        ]
    )
    assert actual == expected


def test_artifact_type_is_string_compatible():
    """``ArtifactType`` inherits from ``str`` so legacy code comparing the
    artifact_type column to bare string literals keeps working."""
    from common.enums import ArtifactType

    assert ArtifactType.audio == "audio"
    assert ArtifactType.image == "image"
    assert "audio" == ArtifactType.audio.value


def test_new_handlers_use_artifact_type_enum_not_bare_strings():
    """A static-source check: the two Phase 3 handlers that ship real
    artifact registration paths (voice + face) must reference
    ``ArtifactType.<name>.value`` rather than bare string literals.
    Historical handlers (scriptwriter/lipsync/editor/qc/publisher) are
    intentionally exempt — that refactor is out of Phase 3F scope."""
    root = Path(__file__).resolve().parents[2]
    for relpath in ("agents/voice/handler.py", "agents/face/handler.py"):
        text = (root / relpath).read_text(encoding="utf-8")
        # No bare artifact_type="audio" / "image" / "video" / etc.
        for bare in ('artifact_type="audio"', 'artifact_type="image"',
                     'artifact_type="video"', 'artifact_type="json"',
                     'artifact_type="metadata"', 'artifact_type="script"',
                     'artifact_type="final_export"'):
            assert bare not in text, (
                f"{relpath} contains bare-string {bare!r}; use ArtifactType.<name>.value"
            )
        # Affirm at least one ArtifactType.<name>.value reference exists.
        assert "ArtifactType." in text, (
            f"{relpath} doesn't reference ArtifactType — Phase 3F expects it"
        )


# ---------------------------------------------------------------------------
# End-to-end: artifact rows carry the right enum-valued artifact_type
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(tmp_path))

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


def _write_real_wav(path: Path, *, duration_sec: float = 0.3, sample_rate: int = 22050) -> None:
    n_frames = int(duration_sec * sample_rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n_frames)


def _write_min_png(path: Path, width: int = 64, height: int = 64) -> None:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = (
        b"\x00\x00\x00\x0d"
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
    tail = b"\x00\x00\x00\x00IEND\xae\x42\x60\x82"
    path.write_bytes(sig + ihdr + tail)


async def test_audio_artifact_uses_artifact_type_audio(app_under_test):
    from agents.orchestrator.dag import DagRunner, DagRunnerConfig
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact
    from common.enums import ArtifactType

    client, _, tmp_path = app_under_test
    audio = tmp_path / "narration.wav"
    _write_real_wav(audio)
    payload = {
        "brief": "Sleep tips.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "voice_mode": "provided_audio",
        "audio_ref": {
            "type": "local_path",
            "path": str(audio),
            "mime_type": "audio/wav",
            "consent_confirmed": True,
            "synthetic_or_owned_voice": True,
        },
    }
    r = await client.post("/jobs", json=payload)
    job_id = uuid.UUID(r.json()["id"])
    cfg = DagRunnerConfig(
        signing_key="phase3f-test", allowed_lipsync_backend="sadtalker"
    )
    final = await DagRunner(get_sessionmaker(), cfg).run(job_id)
    assert final.value == "published"

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(
                Artifact.job_id == job_id,
                Artifact.artifact_type == ArtifactType.audio.value,
            )
        )
        rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].artifact_type == ArtifactType.audio.value


async def test_image_artifact_uses_artifact_type_image(app_under_test):
    from agents.orchestrator.dag import DagRunner, DagRunnerConfig
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact
    from common.enums import ArtifactType

    client, _, tmp_path = app_under_test
    portrait = tmp_path / "portrait.png"
    _write_min_png(portrait, 128, 128)
    payload = {
        "brief": "Sleep tips.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "script_text": "Tip one: avoid screens.",
        "face_mode": "provided_image",
        "image_ref": {
            "type": "local_path",
            "path": str(portrait),
            "mime_type": "image/png",
            "consent_confirmed": True,
            "synthetic_person_confirmed": True,
        },
    }
    r = await client.post("/jobs", json=payload)
    job_id = uuid.UUID(r.json()["id"])
    cfg = DagRunnerConfig(
        signing_key="phase3f-test", allowed_lipsync_backend="sadtalker"
    )
    final = await DagRunner(get_sessionmaker(), cfg).run(job_id)
    assert final.value == "published"

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(
                Artifact.job_id == job_id,
                Artifact.artifact_type == ArtifactType.image.value,
            )
        )
        rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].artifact_type == ArtifactType.image.value
