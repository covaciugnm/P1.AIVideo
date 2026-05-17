"""Phase 11G — Ollama is documented + configured as an external runtime.

The integration was already wired end-to-end in earlier phases (real
HTTP provider in ``agents/scriptwriter/providers/ollama/provider.py``,
categorised error codes in ``backend/app/api/script.py``, mocked +
opt-in real smoke tests in ``test_phase8g_ollama_generation.py``).
Phase 11G is the gap-closing pass: ``.env.example`` calls out the
recommended lightweight model, ``docker/compose.dev.yml`` explicitly
forwards the env vars on both backend AND orchestrator services,
the Makefile exposes safe operator helpers, and the runbook /
bilingual help corpus make the external nature unmistakable.

These tests pin the documentation + config contract so a future
refactor cannot silently regress the operator's setup story.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO / ".env.example"
COMPOSE = REPO / "docker" / "compose.dev.yml"
RUNBOOK = REPO / "docs" / "runbooks" / "ollama-scriptwriter.md"
MAKEFILE = REPO / "Makefile"
PROV_REG = REPO / "backend" / "app" / "services" / "provider_registry.py"
PROVIDER = REPO / "agents" / "scriptwriter" / "providers" / "ollama" / "provider.py"
HELP_EN = REPO / "frontend" / "lib" / "help" / "dictionaries" / "en.ts"
HELP_RO = REPO / "frontend" / "lib" / "help" / "dictionaries" / "ro.ts"
DICT_EN = REPO / "frontend" / "lib" / "i18n" / "dictionaries" / "en.ts"
DICT_RO = REPO / "frontend" / "lib" / "i18n" / "dictionaries" / "ro.ts"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------
# 1-3. .env.example has the canonical env keys.
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
        "OLLAMA_FALLBACK_MODEL",
        "SCRIPTWRITER_ENABLE_NETWORK_CALLS",
        "SCRIPTWRITER_BACKEND",
    ],
)
def test_env_example_declares_key(key):
    text = _read(ENV_EXAMPLE)
    pattern = rf"^{re.escape(key)}\s*="
    assert re.search(pattern, text, re.MULTILINE), (
        f".env.example must declare {key}= so operators see the contract"
    )


def test_env_example_mentions_qwen2_5_7b_as_lightweight_option():
    """Phase 11G — the runbook recommends qwen2.5:7b as a much lighter
    alternative to the project's longstanding qwen3.6 default. The
    env example should mention this so operators don't have to read
    the runbook first."""
    text = _read(ENV_EXAMPLE)
    assert "qwen2.5:7b" in text, (
        ".env.example must mention qwen2.5:7b as the recommended lightweight model"
    )


def test_env_example_says_application_never_auto_pulls():
    text = _read(ENV_EXAMPLE)
    lowered = text.lower()
    assert "auto-pull" in lowered or "never auto-pull" in lowered, (
        ".env.example must explicitly say the application never auto-pulls models"
    )


# ---------------------------------------------------------------------
# 4-7. Runbook documents the operator-facing contract.
# ---------------------------------------------------------------------


def test_runbook_exists():
    assert RUNBOOK.is_file(), "Missing docs/runbooks/ollama-scriptwriter.md"


def test_runbook_says_external_service():
    text = _read(RUNBOOK).lower()
    assert "external" in text, "Runbook must say Ollama is an external service"


def test_runbook_documents_pull_and_network_gate():
    text = _read(RUNBOOK)
    assert "ollama pull qwen2.5:7b" in text, (
        "Runbook must show `ollama pull qwen2.5:7b` as the recommended example"
    )
    assert "SCRIPTWRITER_ENABLE_NETWORK_CALLS=true" in text


def test_runbook_states_no_auto_pull():
    text = _read(RUNBOOK).lower()
    assert "never auto-pull" in text or "no auto-pull" in text, (
        "Runbook must explicitly say the application never auto-pulls"
    )


@pytest.mark.parametrize(
    "code",
    [
        "script_provider_disabled",
        "script_provider_unreachable",
        "script_model_missing",
        "script_generation_failed",
    ],
)
def test_runbook_documents_error_code(code):
    text = _read(RUNBOOK)
    assert code in text, f"Runbook must document the {code} error code"


# ---------------------------------------------------------------------
# 8. Compose explicitly forwards the env vars on backend + orchestrator.
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
        "OLLAMA_FALLBACK_MODEL",
        "SCRIPTWRITER_ENABLE_NETWORK_CALLS",
    ],
)
def test_compose_forwards_env_var(key):
    text = _read(COMPOSE)
    # Must appear at least twice — once for backend, once for orchestrator.
    occurrences = len(re.findall(rf"\b{re.escape(key)}\b", text))
    assert occurrences >= 2, (
        f"compose.dev.yml must explicitly forward {key} on both backend "
        f"AND orchestrator (found {occurrences} mentions)"
    )


def test_compose_adds_host_docker_internal_extra_hosts():
    """Phase 11G — on Linux ``host.docker.internal`` does not auto-map;
    extra_hosts: host-gateway is needed so the backend container can
    reach a host-side Ollama daemon."""
    text = _read(COMPOSE)
    assert "host.docker.internal:host-gateway" in text, (
        "compose.dev.yml must add extra_hosts mapping for host.docker.internal "
        "so Linux operators can run Ollama on the host"
    )


# ---------------------------------------------------------------------
# 9. Makefile exposes safe diagnostic helpers (no auto-pull).
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "target",
    ["ollama-status", "ollama-models", "ollama-smoke"],
)
def test_makefile_target_present(target):
    text = _read(MAKEFILE)
    assert f"\n{target}:" in text, f"Makefile must expose `{target}` target"


def test_makefile_does_not_define_auto_pull_target():
    """The Makefile must NOT define a target whose name suggests
    automatic model download — every pull is an explicit operator
    action."""
    text = _read(MAKEFILE)
    # Allow a hypothetical `ollama-pull-<explicit>` target if it ever
    # ships, as long as it is named after a specific model. The
    # forbidden pattern is a generic `ollama-pull` target with no
    # required argument.
    assert re.search(r"^\nollama-pull\s*:", text, re.MULTILINE) is None, (
        "Makefile must not expose a bare `ollama-pull:` target — every "
        "pull must be operator-explicit"
    )


# ---------------------------------------------------------------------
# 10. Provider registry exposes ollama; provider class has real HTTP.
# ---------------------------------------------------------------------


def test_provider_registry_includes_ollama():
    text = _read(PROV_REG)
    assert '"ollama"' in text, "provider_registry must include ollama"


def test_ollama_provider_uses_real_http():
    text = _read(PROVIDER)
    # The provider must speak HTTP to /api/chat — not stub a fake.
    assert "/api/chat" in text or "/api/generate" in text, (
        "OllamaProvider must actually call the Ollama HTTP API"
    )
    # It must read OLLAMA_BASE_URL + OLLAMA_MODEL from env.
    assert "OLLAMA_BASE_URL" in text
    assert "OLLAMA_MODEL" in text


# ---------------------------------------------------------------------
# 11. Help corpus + error glossary surface the operator-facing story.
# ---------------------------------------------------------------------


@pytest.mark.parametrize("help_file", [HELP_EN, HELP_RO])
def test_help_topic_explicitly_calls_ollama_external(help_file):
    text = _read(help_file)
    block = re.search(
        r'id:\s*"ollama"[\s\S]*?related:', text
    )
    assert block, f"{help_file.name} missing the ollama topic"
    body = block.group(0).lower()
    # Must say "external" + "not installed" in some form (EN: "external",
    # "not installed"; RO: "extern", "nu este instalat").
    assert "external" in body or "extern" in body
    assert "not installed" in body or "nu este instalat" in body


@pytest.mark.parametrize("help_file", [HELP_EN, HELP_RO])
def test_help_topic_mentions_pull_and_gate(help_file):
    text = _read(help_file)
    block = re.search(r'id:\s*"ollama"[\s\S]*?related:', text)
    assert block
    body = block.group(0)
    assert "ollama pull" in body
    assert "SCRIPTWRITER_ENABLE_NETWORK_CALLS" in body


@pytest.mark.parametrize(
    "key",
    [
        "script_provider_disabled",
        "script_provider_unreachable",
        "script_model_missing",
        "script_generation_failed",
    ],
)
def test_error_glossary_has_key(key):
    for path in (DICT_EN, DICT_RO):
        text = _read(path)
        assert re.search(rf"\n\s+{re.escape(key)}:\s*\"", text), (
            f"{path.name} missing errors.{key}"
        )
