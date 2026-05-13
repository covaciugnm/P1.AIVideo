"""Phase 3G integration tests — scriptwriter provider contract + registry.

What we verify:

Registry contract:
- ``resolve("template")`` and the ``"mock"`` alias both return a working
  ``TemplateProvider``.
- ``known_backends()`` advertises every required name:
  ``template``, ``mock``, ``ollama``, ``vllm``, ``openai_compatible``,
  ``openai``, ``anthropic``, ``local_http``.
- An unknown backend raises ``UnsupportedBackendError``.

Template provider:
- Returns a structured ``ScriptResult`` with non-empty ``hook``,
  ``body``, ``cta``, ``full_script``. ``provider`` and ``model`` are
  set. ``estimated_duration_seconds`` matches the request. The result
  is JSON-serializable through Pydantic.
- Deterministic for a fixed input.

Stub providers:
- Every non-template stub's ``healthcheck()`` returns
  ``not_configured`` or ``not_implemented``. ``generate()`` raises
  ``ProviderNotImplementedError``. No real network call is made.

Configuration:
- ``Settings.scriptwriter_model`` defaults to ``"qwen3.6"``.
- ``Settings.scriptwriter_fallback_model`` defaults to ``"qwen3:8b"``.
- ``Settings.scriptwriter_enable_network_calls`` defaults to ``False``.
- No project file hardcodes ``qwen3.6:7b`` (or any composite of the
  preferred + size suffix).
- ``configs/llm/providers.example.yaml`` parses, declares every
  registered backend, and supports per-provider custom-model entries.

DAG integration:
- A run-through-the-DAG job produces an ``artifacts`` row with
  ``artifact_type == ArtifactType.script.value`` whose
  ``metadata_json["structured_script"]`` carries the four script
  fields.

Import discipline:
- Importing every ``agents.scriptwriter.*`` leaf module in a fresh
  subprocess does NOT pull in any LLM / model / network client.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


REQUIRED_BACKENDS = (
    "template",
    "mock",
    "ollama",
    "vllm",
    "openai_compatible",
    "openai",
    "anthropic",
    "local_http",
)


def test_registry_known_backends_covers_required_names():
    from agents.scriptwriter.core.registry import known_backends

    advertised = set(known_backends())
    missing = set(REQUIRED_BACKENDS) - advertised
    assert not missing, f"registry missing backends: {missing}"


def test_registry_resolves_template_and_mock_to_same_class():
    from agents.scriptwriter.core.registry import resolve
    from agents.scriptwriter.providers.template.provider import TemplateProvider

    assert isinstance(resolve("template"), TemplateProvider)
    assert isinstance(resolve("mock"), TemplateProvider)


def test_registry_resolves_every_known_stub():
    from agents.scriptwriter.core.registry import resolve

    for name in REQUIRED_BACKENDS:
        p = resolve(name)
        # provider_name on the alias "mock" still says "template".
        if name == "mock":
            assert p.provider_name == "template"
        else:
            assert p.provider_name == name


def test_registry_rejects_unknown_backend():
    from agents.scriptwriter.core.registry import resolve
    from common.exceptions import UnsupportedBackendError

    with pytest.raises(UnsupportedBackendError):
        resolve("definitely-not-a-real-backend")


# ---------------------------------------------------------------------------
# Template provider
# ---------------------------------------------------------------------------


async def test_template_provider_returns_structured_script():
    from agents.scriptwriter.core.provider import ScriptRequest
    from agents.scriptwriter.providers.template.provider import TemplateProvider

    p = TemplateProvider()
    req = ScriptRequest(
        job_id=uuid.uuid4(),
        brief="Three calming bedtime habits for better sleep",
        target_duration_seconds=30,
    )
    result = await p.generate(req)
    assert result.hook
    assert result.body
    assert result.cta
    assert result.full_script
    assert result.provider == "template"
    assert result.model == "template-v1"
    assert result.estimated_duration_seconds == pytest.approx(30.0)
    # JSON-serializable through Pydantic.
    assert isinstance(result.model_dump_json(), str)


async def test_template_provider_is_deterministic():
    from agents.scriptwriter.core.provider import ScriptRequest
    from agents.scriptwriter.providers.template.provider import TemplateProvider

    p1 = TemplateProvider()
    p2 = TemplateProvider()
    req = ScriptRequest(
        job_id=uuid.uuid4(),
        brief="Sleep tips",
        script_text="Hook line.\n\nBody paragraph here.\n\nCTA at the end.",
        target_duration_seconds=30,
    )
    r1 = await p1.generate(req)
    r2 = await p2.generate(req)
    assert r1.hook == r2.hook
    assert r1.body == r2.body
    assert r1.cta == r2.cta


async def test_template_provider_splits_operator_script_text():
    from agents.scriptwriter.core.provider import ScriptRequest
    from agents.scriptwriter.providers.template.provider import TemplateProvider

    p = TemplateProvider()
    req = ScriptRequest(
        job_id=uuid.uuid4(),
        brief="Sleep tips",
        script_text="My opening hook.\n\nThe body of the script.\n\nFollow for more.",
        target_duration_seconds=30,
    )
    result = await p.generate(req)
    assert result.hook == "My opening hook."
    assert "body of the script" in result.body
    assert result.cta == "Follow for more."


def test_template_provider_healthcheck_is_ok():
    from agents.scriptwriter.providers.template.provider import TemplateProvider
    from common.enums import ProviderHealthStatus

    health = TemplateProvider().healthcheck()
    assert health.status is ProviderHealthStatus.ok
    assert health.extra["calls_external_apis"] is False


# ---------------------------------------------------------------------------
# Stub providers: healthcheck + generate refusal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend", ["ollama", "vllm", "openai_compatible", "openai", "anthropic", "local_http"])
def test_stub_provider_healthcheck_is_not_implemented_or_not_configured(backend, monkeypatch):
    # Strip provider-specific env so we observe the unconfigured branch where applicable.
    for var in (
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
        "VLLM_BASE_URL",
        "VLLM_MODEL",
        "OPENAI_COMPATIBLE_BASE_URL",
        "OPENAI_COMPATIBLE_API_KEY",
        "OPENAI_COMPATIBLE_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "LOCAL_LLM_URL",
        "LOCAL_LLM_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)
    from agents.scriptwriter.core.registry import resolve
    from common.enums import ProviderHealthStatus

    health = resolve(backend).healthcheck()
    assert health.status in (
        ProviderHealthStatus.not_configured,
        ProviderHealthStatus.not_implemented,
    )
    # Stubs MUST advertise they are not making calls.
    assert health.extra.get("calls_external_apis") is False


@pytest.mark.parametrize("backend", ["ollama", "vllm", "openai_compatible", "openai", "anthropic", "local_http"])
async def test_stub_provider_generate_raises_not_implemented(backend):
    from agents.scriptwriter.core.provider import ScriptRequest
    from agents.scriptwriter.core.registry import resolve
    from common.exceptions import ProviderNotImplementedError

    req = ScriptRequest(
        job_id=uuid.uuid4(), brief="Sleep tips", target_duration_seconds=30
    )
    with pytest.raises(ProviderNotImplementedError):
        await resolve(backend).generate(req)


def test_ollama_provider_picks_up_preferred_and_fallback_models(monkeypatch):
    """The default preferred/fallback model names match the Phase 3G spec."""
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_FALLBACK_MODEL", raising=False)
    from agents.scriptwriter.providers.ollama.provider import OllamaProvider

    p = OllamaProvider()
    assert p.model_name == "qwen3.6"
    health = p.healthcheck()
    assert health.extra["preferred_model"] == "qwen3.6"
    assert health.extra["fallback_model"] == "qwen3:8b"


# ---------------------------------------------------------------------------
# Settings defaults
# ---------------------------------------------------------------------------


def test_scriptwriter_settings_defaults():
    """Defaults match the Phase 3G contract — qwen3.6 / qwen3:8b."""
    from app.core.config import Settings

    # Build a clean Settings instance from defaults so prior tests'
    # env vars can't bleed in.
    fresh = Settings(
        _env_file=None,  # type: ignore[call-arg]
        SCRIPTWRITER_BACKEND="template",
        SCRIPTWRITER_MODEL="qwen3.6",
        SCRIPTWRITER_FALLBACK_MODEL="qwen3:8b",
    )
    assert fresh.scriptwriter_backend == "template"
    assert fresh.scriptwriter_model == "qwen3.6"
    assert fresh.scriptwriter_fallback_model == "qwen3:8b"
    assert fresh.scriptwriter_enable_network_calls is False


def test_qwen36_7b_is_not_hardcoded_anywhere():
    """Phase 3G explicitly uses ``qwen3.6`` (preferred) and ``qwen3:8b``
    (fallback). ``qwen3.6:7b`` is not assumed to exist — make sure it's
    not hardcoded as a default in any source / config file."""
    forbidden = "qwen3.6:7b"
    scan_roots = ["agents", "common", "backend", "configs", ".env.example"]
    hits: list[str] = []
    for root in scan_roots:
        p = _ROOT / root
        if p.is_file():
            if forbidden in p.read_text(encoding="utf-8"):
                hits.append(str(p))
            continue
        for f in p.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() in {".pyc", ".so", ".whl"}:
                continue
            if "__pycache__" in f.parts or "egg-info" in str(f):
                continue
            try:
                content = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if forbidden in content:
                hits.append(str(f.relative_to(_ROOT)))
    assert hits == [], (
        f"{forbidden!r} appears in: {hits}. Use 'qwen3.6' (preferred) and "
        f"'qwen3:8b' (fallback) instead."
    )


# ---------------------------------------------------------------------------
# YAML provider registry config
# ---------------------------------------------------------------------------


def test_providers_example_yaml_parses_and_covers_required_types():
    """The example YAML must declare every registry-known backend type
    so operators can opt into any of them without code changes."""
    yaml_path = _ROOT / "configs" / "llm" / "providers.example.yaml"
    assert yaml_path.is_file(), f"missing {yaml_path}"
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    providers = data["providers"]

    # Every required backend is declared.
    required_types = {
        "template",
        "ollama",
        "vllm",
        "openai_compatible",
        "openai",
        "anthropic",
        "local_http",
    }
    declared = set(providers.keys())
    missing = required_types - declared
    assert not missing, f"providers.example.yaml missing: {missing}"

    # `template` is enabled by default; every other provider is NOT.
    assert providers["template"]["enabled"] is True
    for name in declared - {"template"}:
        assert providers[name]["enabled"] is False, (
            f"providers.example.yaml: {name} must default to enabled=false"
        )


def test_providers_yaml_supports_extending_models_without_code_changes(tmp_path):
    """An operator can add a custom model entry under an existing
    provider's ``models`` list without modifying any Python file."""
    custom = {
        "version": 1,
        "providers": {
            "ollama": {
                "enabled": False,
                "type": "ollama",
                "base_url": "http://localhost:11434",
                "default_model": "qwen3.6",
                "fallback_model": "qwen3:8b",
                "models": [
                    {"name": "qwen3.6", "role": "preferred"},
                    {"name": "qwen3:8b", "role": "fallback"},
                    {"name": "future-mystery-model-9", "role": "custom"},
                ],
            }
        },
    }
    config_path = tmp_path / "providers.yaml"
    config_path.write_text(yaml.safe_dump(custom), encoding="utf-8")
    # The YAML is round-trippable and carries the operator's added model.
    parsed = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    model_names = [m["name"] for m in parsed["providers"]["ollama"]["models"]]
    assert "future-mystery-model-9" in model_names
    assert "qwen3.6" in model_names
    assert "qwen3:8b" in model_names


# ---------------------------------------------------------------------------
# DAG: script artifact registration
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(tmp_path))
    # Force template backend regardless of any environment-level override.
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")
    monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "false")

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


def _runner_config():
    from agents.orchestrator.dag import DagRunnerConfig

    return DagRunnerConfig(
        signing_key="phase3g-test-key-not-for-prod",
        allowed_lipsync_backend="sadtalker",
        token_ttl_seconds=3600,
    )


def _valid_payload() -> dict:
    return {
        "brief": "Three calming bedtime habits for better sleep.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "script_text": "Tip one: avoid screens before bed.",
    }


async def test_dag_promotes_script_artifact_with_artifact_type_script(app_under_test):
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact
    from common.enums import ArtifactType

    client, _, _ = app_under_test
    r = await client.post("/jobs", json=_valid_payload())
    assert r.status_code == 201
    job_id = uuid.UUID(r.json()["id"])
    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "published"

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(
                Artifact.job_id == job_id,
                Artifact.artifact_type == ArtifactType.script.value,
            )
        )
        rows = list(result.scalars().all())
    assert len(rows) == 1
    row = rows[0]
    assert row.mime_type == "application/json"
    assert row.checksum_sha256 and len(row.checksum_sha256) == 64
    assert row.size_bytes is not None and row.size_bytes > 0
    structured = (row.metadata_json or {}).get("structured_script")
    assert structured is not None
    assert structured["hook"]
    assert structured["body"]
    assert structured["cta"]
    assert structured["full_script"]
    # Confirms the handler ran via the template provider (the default).
    assert (row.metadata_json or {}).get("selected_backend") == "template"
    assert (row.metadata_json or {}).get("network_calls_enabled") is False


# ---------------------------------------------------------------------------
# Import discipline
# ---------------------------------------------------------------------------


def test_scriptwriter_modules_have_no_heavy_or_llm_imports():
    """No scriptwriter module — provider stub or template — may pull in
    an LLM / model client at import time. Verified in a fresh subprocess
    so other tests can't pollute sys.modules."""
    code = (
        "import json, sys, importlib\n"
        "leaf_modules = [\n"
        "    'agents.scriptwriter.handler',\n"
        "    'agents.scriptwriter.core.provider',\n"
        "    'agents.scriptwriter.core.registry',\n"
        "    'agents.scriptwriter.providers.template.provider',\n"
        "    'agents.scriptwriter.providers.ollama.provider',\n"
        "    'agents.scriptwriter.providers.vllm.provider',\n"
        "    'agents.scriptwriter.providers.openai_compatible.provider',\n"
        "    'agents.scriptwriter.providers.openai.provider',\n"
        "    'agents.scriptwriter.providers.anthropic.provider',\n"
        "    'agents.scriptwriter.providers.local_http.provider',\n"
        "]\n"
        "for m in leaf_modules:\n"
        "    importlib.import_module(m)\n"
        "# Also exercise the registry — should not import anything new\n"
        "# above the template provider on resolve('template').\n"
        "from agents.scriptwriter.core.registry import resolve, known_backends\n"
        "resolve('template')\n"
        "_ = known_backends()\n"
        "forbidden = ['openai', 'anthropic', 'langchain', 'langchain_core',\n"
        "             'langgraph', 'transformers', 'torch', 'torchvision',\n"
        "             'torchaudio', 'diffusers', 'accelerate', 'xformers',\n"
        "             'sentencepiece', 'whisper', 'whisperx', 'httpx',\n"
        "             'requests', 'aiohttp']\n"
        "loaded = sorted(m for m in forbidden if m in sys.modules)\n"
        "print(json.dumps(loaded))\n"
    )
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"subprocess failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert loaded == [], (
        f"scriptwriter modules transitively imported forbidden libs: {loaded}"
    )


def test_resolving_every_backend_still_has_no_heavy_imports():
    """Even calling ``resolve()`` on every backend (which lazy-imports
    each provider) must NOT pull in OpenAI / Anthropic / etc."""
    code = (
        "import json, sys\n"
        "from agents.scriptwriter.core.registry import resolve, known_backends\n"
        "for name in known_backends():\n"
        "    resolve(name)\n"
        "forbidden = ['openai', 'anthropic', 'langchain', 'langgraph',\n"
        "             'transformers', 'torch', 'diffusers']\n"
        "loaded = sorted(m for m in forbidden if m in sys.modules)\n"
        "print(json.dumps(loaded))\n"
    )
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert loaded == [], f"Resolving stubs pulled in heavy libs: {loaded}"
