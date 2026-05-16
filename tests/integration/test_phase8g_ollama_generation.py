"""Phase 8G — Ollama real generation (mocked + opt-in smoke).

The runtime path POSTs to a local Ollama daemon via stdlib
``urllib.request``. These tests use a tiny in-process HTTP server
(stdlib ``http.server.BaseHTTPRequestHandler``) so we can pin every
branch — daemon unreachable, model missing, malformed reply, fallback,
JSON-mode success, plain-text segmentation — without touching the real
network. Default test runs **never** call a real Ollama daemon.

An opt-in real smoke test at the bottom requires
``RUN_REAL_OLLAMA_SMOKE=1`` + ``SCRIPTWRITER_ENABLE_NETWORK_CALLS=true``
+ ``OLLAMA_BASE_URL`` set to a reachable daemon (e.g.
``http://172.17.0.1:11434`` from inside Docker).
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Iterator

import pytest


# ---------------------------------------------------------------------------
# Tiny in-process Ollama mock server
# ---------------------------------------------------------------------------


class _OllamaScript:
    """Programmable response set for one test run. Each test instantiates
    one and feeds it to ``_mock_ollama_server`` so we can vary tags +
    chat replies without spinning up real Ollama."""

    def __init__(
        self,
        *,
        tags: list[str] | None = None,
        chat_responses: dict[str, dict[str, Any]] | None = None,
        chat_status_overrides: dict[str, int] | None = None,
    ) -> None:
        self.tags = tags or []
        # Maps model_name → JSON response body to return from /api/chat.
        self.chat_responses = chat_responses or {}
        # Maps model_name → custom HTTP status (404 = model missing).
        self.chat_status_overrides = chat_status_overrides or {}
        self.calls: list[dict[str, Any]] = []


@contextmanager
def _mock_ollama_server(script: _OllamaScript) -> Iterator[str]:
    """Spawn a daemon HTTP server on a free port; yield the base URL."""

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *args, **kwargs):  # noqa: ARG002 — silence
            return

        def do_GET(self):
            if self.path == "/api/tags":
                body = json.dumps(
                    {"models": [{"name": t} for t in script.tags]}
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body_in = self.rfile.read(length)
            try:
                payload = json.loads(body_in or b"{}")
            except json.JSONDecodeError:
                payload = {}
            script.calls.append({"path": self.path, "payload": payload})

            if self.path != "/api/chat":
                self.send_response(404)
                self.end_headers()
                return

            model = payload.get("model")
            status = script.chat_status_overrides.get(model, 200)
            if status == 200 and model in script.chat_responses:
                body = json.dumps(script.chat_responses[model]).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if status == 404:
                body = json.dumps(
                    {"error": f"model {model!r} not found"}
                ).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
                return

            # default unhandled → 500
            self.send_response(500)
            self.end_headers()

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _build_request(brief: str = "Phase 8G smoke") -> "ScriptRequest":
    from agents.scriptwriter.core.provider import ScriptRequest

    return ScriptRequest(
        job_id=uuid.uuid4(),
        brief=brief,
        target_duration_seconds=30,
        language="en",
    )


# ---------------------------------------------------------------------------
# Module-load isolation — no network, no heavy deps at import time
# ---------------------------------------------------------------------------


def test_provider_module_has_no_heavy_imports_at_load():
    """Importing the OllamaProvider module must not contact Ollama and
    must not pull torch / requests / httpx into sys.modules. Stdlib
    urllib only."""
    import subprocess
    import sys
    from pathlib import Path

    code = (
        "import sys\n"
        "import agents.scriptwriter.providers.ollama.provider  # noqa: F401\n"
        "forbidden = ('torch','httpx','requests','aiohttp','ollama','openai')\n"
        "print(','.join(sorted(m for m in forbidden if m in sys.modules)))\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Network-disabled gate (default behavior)
# ---------------------------------------------------------------------------


async def test_generate_raises_when_network_disabled(monkeypatch):
    """The whole point of SCRIPTWRITER_ENABLE_NETWORK_CALLS — if it's
    off, ``generate()`` must short-circuit without opening a socket."""
    monkeypatch.delenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")  # closed port
    from agents.scriptwriter.providers.ollama.provider import OllamaProvider
    from common.exceptions import ProviderNotImplementedError

    provider = OllamaProvider()
    with pytest.raises(ProviderNotImplementedError) as exc:
        await provider.generate(_build_request())
    assert "SCRIPTWRITER_ENABLE_NETWORK_CALLS" in str(exc.value)


def test_healthcheck_reports_not_implemented_when_network_disabled(monkeypatch):
    monkeypatch.delenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", raising=False)
    from agents.scriptwriter.providers.ollama.provider import OllamaProvider

    health = OllamaProvider().healthcheck()
    assert health.status.value == "not_implemented"


# ---------------------------------------------------------------------------
# Unreachable daemon
# ---------------------------------------------------------------------------


async def test_unreachable_daemon_raises_unreachable(monkeypatch):
    monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")  # closed
    from agents.scriptwriter.providers.ollama.provider import OllamaProvider
    from common.exceptions import ProviderNotImplementedError

    provider = OllamaProvider()
    with pytest.raises(ProviderNotImplementedError) as exc:
        await provider.generate(_build_request())
    assert str(exc.value).startswith("unreachable:")


def test_unreachable_daemon_healthcheck_returns_not_configured(monkeypatch):
    monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")
    from agents.scriptwriter.providers.ollama.provider import OllamaProvider

    health = OllamaProvider().healthcheck()
    assert health.status.value == "not_configured"


# ---------------------------------------------------------------------------
# Model missing (404 on /api/chat) + fallback
# ---------------------------------------------------------------------------


async def test_primary_model_404_falls_back_to_secondary(monkeypatch):
    script = _OllamaScript(
        tags=["qwen3.6:latest", "qwen3:8b"],
        chat_status_overrides={"qwen3.6": 404},
        chat_responses={
            "qwen3:8b": {
                "model": "qwen3:8b",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "hook": "Quick test",
                            "body": "Hello from qwen3:8b fallback.",
                            "cta": "Subscribe.",
                            "full_script": "Quick test\n\nHello from qwen3:8b fallback.\n\nSubscribe.",
                            "estimated_duration_seconds": 12,
                            "language": "en",
                        }
                    ),
                },
                "done": True,
            }
        },
    )
    with _mock_ollama_server(script) as base:
        monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
        monkeypatch.setenv("OLLAMA_BASE_URL", base)
        monkeypatch.setenv("OLLAMA_MODEL", "qwen3.6")
        monkeypatch.setenv("OLLAMA_FALLBACK_MODEL", "qwen3:8b")
        from agents.scriptwriter.providers.ollama.provider import OllamaProvider

        result = await OllamaProvider().generate(_build_request())
        assert result.model == "qwen3:8b"
        assert "qwen3:8b fallback" in result.body
        assert result.metadata["tried_models"] == ["qwen3.6", "qwen3:8b"]


async def test_all_models_404_raises_model_missing(monkeypatch):
    script = _OllamaScript(
        tags=[],
        chat_status_overrides={"qwen3.6": 404, "qwen3:8b": 404},
    )
    with _mock_ollama_server(script) as base:
        monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
        monkeypatch.setenv("OLLAMA_BASE_URL", base)
        from agents.scriptwriter.providers.ollama.provider import OllamaProvider
        from common.exceptions import ProviderNotImplementedError

        with pytest.raises(ProviderNotImplementedError) as exc:
            await OllamaProvider().generate(_build_request())
        assert str(exc.value).startswith("model_missing:")


def test_healthcheck_reports_missing_assets_when_neither_model_present(monkeypatch):
    script = _OllamaScript(tags=["llama3.1:8b"])  # neither qwen present
    with _mock_ollama_server(script) as base:
        monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
        monkeypatch.setenv("OLLAMA_BASE_URL", base)
        from agents.scriptwriter.providers.ollama.provider import OllamaProvider

        health = OllamaProvider().healthcheck()
        assert health.status.value == "missing_assets"
        assert "qwen3.6" in (health.missing_assets or [])


# ---------------------------------------------------------------------------
# Happy path — JSON-mode response
# ---------------------------------------------------------------------------


async def test_json_response_parses_into_structured_script(monkeypatch):
    payload = {
        "hook": "Tiny bakery, big flavors.",
        "body": "Discover three reasons our local bakery is your next stop.",
        "cta": "Stop by today!",
        "full_script": "Tiny bakery, big flavors.\n\nDiscover three reasons our local bakery is your next stop.\n\nStop by today!",
        "estimated_duration_seconds": 28,
        "language": "en",
    }
    script = _OllamaScript(
        tags=["qwen3.6:latest"],
        chat_responses={
            "qwen3.6": {
                "model": "qwen3.6:latest",
                "message": {"role": "assistant", "content": json.dumps(payload)},
                "done": True,
            }
        },
    )
    with _mock_ollama_server(script) as base:
        monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
        monkeypatch.setenv("OLLAMA_BASE_URL", base)
        from agents.scriptwriter.providers.ollama.provider import OllamaProvider

        result = await OllamaProvider().generate(_build_request(brief="bakery"))
        assert result.hook == payload["hook"]
        assert result.body == payload["body"]
        assert result.cta == payload["cta"]
        assert result.estimated_duration_seconds == 28
        assert result.provider == "ollama"
        assert result.model == "qwen3.6"
        assert result.metadata["json_parsed"] is True


# ---------------------------------------------------------------------------
# Plain-text response → deterministic segmentation
# ---------------------------------------------------------------------------


async def test_plain_text_response_falls_back_to_sentence_segmentation(monkeypatch):
    raw = (
        "Welcome to the local bakery. We use fresh ingredients every morning."
        " Stop by and grab a treat."
    )
    script = _OllamaScript(
        tags=["qwen3.6:latest"],
        chat_responses={
            "qwen3.6": {
                "model": "qwen3.6:latest",
                "message": {"role": "assistant", "content": raw},
                "done": True,
            }
        },
    )
    with _mock_ollama_server(script) as base:
        monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
        monkeypatch.setenv("OLLAMA_BASE_URL", base)
        from agents.scriptwriter.providers.ollama.provider import OllamaProvider

        result = await OllamaProvider().generate(_build_request())
        assert "bakery" in result.hook.lower()
        assert result.cta  # non-empty
        assert result.metadata["json_parsed"] is False


# ---------------------------------------------------------------------------
# Malformed response envelope → script_generation_failed via prefix
# ---------------------------------------------------------------------------


async def test_envelope_missing_message_raises_malformed(monkeypatch):
    script = _OllamaScript(
        tags=["qwen3.6:latest"],
        chat_responses={"qwen3.6": {"done": True}},  # no "message" key
    )
    with _mock_ollama_server(script) as base:
        monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
        monkeypatch.setenv("OLLAMA_BASE_URL", base)
        from agents.scriptwriter.providers.ollama.provider import OllamaProvider
        from common.exceptions import ProviderNotImplementedError

        with pytest.raises(ProviderNotImplementedError) as exc:
            await OllamaProvider().generate(_build_request())
        assert str(exc.value).startswith("malformed_response:")


# ---------------------------------------------------------------------------
# Project invariants
# ---------------------------------------------------------------------------


def test_qwen36_default_and_qwen3_8b_fallback(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_FALLBACK_MODEL", raising=False)
    from agents.scriptwriter.providers.ollama.provider import OllamaProvider

    p = OllamaProvider()
    assert p.model_name == "qwen3.6"
    assert p._fallback_model == "qwen3:8b"  # type: ignore[attr-defined]


def test_qwen36_7b_is_never_hardcoded():
    """Phase 3G drift guard — re-pinned here so a Phase 8G change can't
    accidentally introduce ``qwen3.6:7b`` as a default."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "agents"
        / "scriptwriter"
        / "providers"
        / "ollama"
        / "provider.py"
    ).read_text()
    assert "qwen3.6:7b" not in src


# ---------------------------------------------------------------------------
# Optional real smoke — opt-in via RUN_REAL_OLLAMA_SMOKE=1
# ---------------------------------------------------------------------------


_REAL_SMOKE_ENABLED = os.environ.get("RUN_REAL_OLLAMA_SMOKE", "").lower() in (
    "1",
    "true",
    "yes",
    "on",
)


@pytest.mark.skipif(
    not _REAL_SMOKE_ENABLED,
    reason=(
        "Real Ollama smoke disabled. Set RUN_REAL_OLLAMA_SMOKE=1 + "
        "SCRIPTWRITER_ENABLE_NETWORK_CALLS=true + an OLLAMA_BASE_URL "
        "pointing at a reachable daemon with the configured model "
        "pulled. See docs/runbooks/ollama-scriptwriter.md."
    ),
)
async def test_real_ollama_smoke_when_explicitly_enabled():
    """Hit a real daemon — sanity-check the integration end-to-end.
    The result need not be ``OK``; any of {real script, model_missing,
    unreachable} is acceptable as long as we never crash."""
    os.environ.setdefault("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")
    from agents.scriptwriter.providers.ollama.provider import OllamaProvider
    from common.exceptions import ProviderNotImplementedError

    provider = OllamaProvider()
    try:
        result = await provider.generate(
            _build_request(brief="Three healthy snack ideas for after school.")
        )
    except ProviderNotImplementedError as exc:
        # model_missing / unreachable / malformed_response are all
        # acceptable — just confirm we got a categorised reason.
        assert ":" in str(exc), exc
        return
    assert result.provider == "ollama"
    assert result.hook
    assert result.full_script


_ = time  # silence unused
