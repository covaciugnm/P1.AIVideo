"""Phase 8G-2 — /api/v1/script/generate surfaces ``script_model_missing``
as a distinct error code (was folded into ``script_provider_unreachable``
before).

We monkey-patch the scriptwriter registry to return a fake Ollama
provider whose ``generate()`` raises ``ProviderNotImplementedError``
with the categorised ``model_missing:`` / ``unreachable:`` prefix.
The API mapper at ``backend/app/api/script.py`` must route those to
the right ``script_*`` code without crossing them.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app_under_test(monkeypatch):
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")
    monkeypatch.setenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "true")

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
        yield client
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


def _payload(**overrides) -> dict:
    body = {
        "brief": "Phase 8G-2 model_missing smoke",
        "target_duration_seconds": 30,
        "provider_id": "ollama",
        "model": "qwen3.6",
    }
    body.update(overrides)
    return body


def _patch_registry_with(monkeypatch, raise_msg: str) -> None:
    """Install a fake Ollama provider that raises a categorised
    ProviderNotImplementedError with the given prefixed message."""
    from common.enums import ProviderHealthStatus
    from common.exceptions import ProviderNotImplementedError
    from common.schemas import ProviderHealth

    class _FakeProvider:
        provider_name = "ollama"
        model_name = "qwen3.6"
        supports_streaming = False
        supports_json_mode = True

        def required_config(self):
            return []

        def healthcheck(self) -> ProviderHealth:
            return ProviderHealth(
                backend="ollama", status=ProviderHealthStatus.ok
            )

        async def generate(self, req):
            raise ProviderNotImplementedError(raise_msg)

    import agents.scriptwriter.core.registry as registry

    monkeypatch.setattr(registry, "resolve", lambda name: _FakeProvider())


async def test_model_missing_maps_to_script_model_missing(
    app_under_test, monkeypatch
):
    _patch_registry_with(
        monkeypatch, "model_missing: 'qwen3.6' is not pulled on the daemon"
    )
    r = await app_under_test.post(
        "/api/v1/script/generate", json=_payload()
    )
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "script_model_missing"
    assert "qwen3.6" in detail["message"]
    assert detail["provider_id"] == "ollama"


async def test_unreachable_still_maps_to_script_provider_unreachable(
    app_under_test, monkeypatch
):
    _patch_registry_with(
        monkeypatch, "unreachable: ollama daemon did not respond"
    )
    r = await app_under_test.post(
        "/api/v1/script/generate", json=_payload()
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "script_provider_unreachable"


async def test_malformed_response_maps_to_script_generation_failed(
    app_under_test, monkeypatch
):
    _patch_registry_with(
        monkeypatch, "malformed_response: missing message.content"
    )
    r = await app_under_test.post(
        "/api/v1/script/generate", json=_payload()
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "script_generation_failed"


async def test_script_generate_error_schema_accepts_new_code():
    """Defence-in-depth: the Pydantic Literal union must explicitly
    include ``script_model_missing`` so an old client validating
    against the schema doesn't reject the new code as ``extra``."""
    from app.api.script import ScriptGenerateError

    err = ScriptGenerateError(
        code="script_model_missing",
        message="x",
        provider_id="ollama",
    )
    assert err.code == "script_model_missing"


async def test_unknown_prefix_falls_back_to_unreachable_under_network_on(
    app_under_test, monkeypatch
):
    """ProviderNotImplementedError without a known prefix and network
    calls enabled → keep the legacy ``script_provider_unreachable``."""
    _patch_registry_with(monkeypatch, "something_unrecognised: oops")
    r = await app_under_test.post(
        "/api/v1/script/generate", json=_payload()
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "script_provider_unreachable"


_ = pytest  # placate lint
