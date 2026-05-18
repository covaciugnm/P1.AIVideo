"""Phase 10C — Backend API surface invariants.

Lightweight static check that the routes promised by
``docs/runbooks/api-surface.md`` exist on the live FastAPI app. Catches
the most common drift: someone renames or removes a route and forgets to
update the doc.

The test introspects the app's OpenAPI schema — no real model load, no
network, no DB other than the in-process SQLite.
"""
from __future__ import annotations

import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


# Canonical endpoints the operator-facing dashboard relies on. Mirrors
# docs/runbooks/api-surface.md. Adding a row here without also adding
# the route is a test failure on purpose — the doc is the contract.
REQUIRED_ENDPOINTS: tuple[tuple[str, str], ...] = (
    # Health / system / config
    ("GET", "/healthz"),
    ("GET", "/api/v1/system/status"),
    # Phase 12T — Technical Help (markdown report served from disk)
    ("GET", "/api/v1/system/technical-architecture"),
    ("GET", "/api/v1/system/technical-architecture.md"),
    # Phase 13 — backend log ring buffer (right-sidebar Backend tab)
    ("GET", "/api/v1/system/logs/backend"),
    # Phase 15E — live probe of every model-* wrapper container
    ("GET", "/api/v1/system/wrappers"),
    # Phase 15B — character video library (job deep links)
    ("GET", "/api/v1/characters/{character_id}/videos"),
    ("GET", "/api/v1/config/ui-options"),
    ("GET", "/api/v1/config/languages"),
    ("GET", "/api/v1/stages"),
    ("GET", "/api/v1/artifact-types"),
    # Phase 11A operator settings (singleton row)
    ("GET", "/api/v1/settings/ui"),
    ("PATCH", "/api/v1/settings/ui"),
    # Jobs (canonical)
    ("GET", "/api/v1/jobs"),
    ("POST", "/api/v1/jobs"),
    ("POST", "/api/v1/jobs/from-inputs"),
    ("GET", "/api/v1/jobs/{job_id}"),
    ("PATCH", "/api/v1/jobs/{job_id}"),
    ("DELETE", "/api/v1/jobs/{job_id}"),
    ("GET", "/api/v1/jobs/{job_id}/summary"),
    ("GET", "/api/v1/jobs/{job_id}/progress"),
    ("GET", "/api/v1/jobs/{job_id}/timeline"),
    ("GET", "/api/v1/jobs/{job_id}/artifacts"),
    ("GET", "/api/v1/jobs/{job_id}/compliance-events"),
    ("GET", "/api/v1/jobs/{job_id}/qc-report"),
    ("GET", "/api/v1/jobs/{job_id}/final-export"),
    ("POST", "/api/v1/jobs/{job_id}/cancel"),
    ("POST", "/api/v1/jobs/{job_id}/retry"),
    # Uploads
    ("POST", "/api/v1/uploads/text"),
    ("POST", "/api/v1/uploads/audio"),
    ("POST", "/api/v1/uploads/image"),
    # Artifact content stream
    ("GET", "/api/v1/artifacts/{artifact_id}/content"),
    # Providers
    ("GET", "/api/v1/providers"),
    ("GET", "/api/v1/providers/llm"),
    ("GET", "/api/v1/providers/tts"),
    ("GET", "/api/v1/providers/video-generators"),
    ("GET", "/api/v1/providers/audio-processors"),
    ("GET", "/api/v1/providers/image-processors"),
    ("GET", "/api/v1/providers/{category}/{provider_id}"),
    # Generation
    ("POST", "/api/v1/script/generate"),
    ("POST", "/api/v1/tts/generate"),
    ("POST", "/api/v1/video/generate"),
    # Media tools
    ("POST", "/api/v1/audio/fit-check"),
    ("POST", "/api/v1/qc/inspect"),
    ("POST", "/api/v1/export/finalize"),
    # Phase 12 — Characters / Personas tab.
    ("GET", "/api/v1/characters"),
    ("POST", "/api/v1/characters"),
    ("GET", "/api/v1/characters/lookups"),
    ("GET", "/api/v1/characters/{character_id}"),
    ("PUT", "/api/v1/characters/{character_id}"),
    ("DELETE", "/api/v1/characters/{character_id}"),
    ("GET", "/api/v1/characters/{character_id}/script-context"),
    ("GET", "/api/v1/characters/{character_id}/images"),
    ("POST", "/api/v1/characters/{character_id}/images/generate"),
    ("POST", "/api/v1/characters/{character_id}/images/{image_id}/accept"),
    ("POST", "/api/v1/characters/{character_id}/images/{image_id}/reject"),
    ("POST", "/api/v1/characters/{character_id}/images/{image_id}/set-main-reference"),
    ("POST", "/api/v1/characters/{character_id}/images/{image_id}/archive"),
    ("DELETE", "/api/v1/characters/{character_id}/images/{image_id}"),
    ("GET", "/api/v1/characters/{character_id}/images/{image_id}/content"),
    # Phase 12 — image generator catalog + per-provider health check.
    ("GET", "/api/v1/providers/image-generators"),
    ("POST", "/api/v1/providers/{category}/{provider_id}/health-check"),
    # Phase 12X — DB-backed API key store (right-sidebar Keys page).
    ("GET", "/api/v1/secrets"),
    ("POST", "/api/v1/secrets"),
    ("PUT", "/api/v1/secrets/{key_name}"),
    ("DELETE", "/api/v1/secrets/{key_name}"),
    ("POST", "/api/v1/secrets/{key_name}/test"),
)


@pytest_asyncio.fixture
async def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path / "artifacts"))

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
        yield client

    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


def _index_openapi(spec: dict) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for path, methods in (spec.get("paths") or {}).items():
        for m in methods:
            if m.lower() in {"get", "post", "put", "patch", "delete"}:
                out.add((m.upper(), path))
    return out


async def test_all_required_endpoints_exist(app_client):
    resp = await app_client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    actual = _index_openapi(spec)

    missing = [pair for pair in REQUIRED_ENDPOINTS if pair not in actual]
    assert not missing, (
        "Routes promised by docs/runbooks/api-surface.md are missing from the "
        f"live app: {missing}. Either implement them or update the doc."
    )


async def test_openapi_routes_are_documented(app_client):
    """Every canonical /api/v1 path the app exposes must be claimed by
    REQUIRED_ENDPOINTS (or be an explicit alias / legacy). Catches
    'route added, doc not updated' drift in the other direction.
    """
    resp = await app_client.get("/openapi.json")
    spec = resp.json()
    actual_v1 = {
        (m, p)
        for (m, p) in _index_openapi(spec)
        if p.startswith("/api/v1/")
    }
    known = set(REQUIRED_ENDPOINTS)
    undocumented = actual_v1 - known
    assert not undocumented, (
        "Canonical /api/v1 routes exist but are NOT listed in "
        "docs/runbooks/api-surface.md → REQUIRED_ENDPOINTS. Add them: "
        f"{sorted(undocumented)}"
    )


async def test_health_and_system_status_are_clean_json(app_client):
    """Smoke-check that the two surfaces the dashboard polls every few
    seconds return valid JSON with the expected keys. Catches the case
    where someone refactors them into HTML / 500.
    """
    h = await app_client.get("/healthz")
    assert h.status_code == 200
    body = h.json()
    assert body.get("status") == "ok"

    s = await app_client.get("/api/v1/system/status")
    assert s.status_code == 200
    sbody = s.json()
    for required_key in (
        "app_name",
        "app_version",
        "server_time",
        "database_reachable",
    ):
        assert required_key in sbody, f"missing key {required_key!r}: {sbody}"


async def test_provider_lists_are_arrays(app_client):
    """Every provider category endpoint must return a JSON array (not a
    dict, not a string). Catches the regression where the provider
    registry collapses to a single dict on misconfiguration.
    """
    for slug in (
        "llm",
        "tts",
        "video-generators",
        "audio-processors",
        "image-processors",
    ):
        r = await app_client.get(f"/api/v1/providers/{slug}")
        assert r.status_code == 200, (slug, r.text)
        data = r.json()
        assert isinstance(data, list), f"{slug} → {type(data).__name__}, want list"
        # Every row must have provider_id + status (the catalog invariants).
        for row in data:
            assert "provider_id" in row, (slug, row)
            assert "status" in row, (slug, row)


async def test_generate_endpoints_reject_invalid_inputs_cleanly(app_client):
    """Bad requests should return categorised JSON, never HTML or
    tracebacks. This is the cheapest guard against the 'frontend gets
    raw 500 page' regression.
    """
    # Script generate — bogus provider id should still return a
    # categorised 503/422 with a JSON body.
    r = await app_client.post(
        "/api/v1/script/generate",
        json={
            "brief": "test",
            "target_duration_seconds": 30,
            "provider_id": "this-provider-does-not-exist-1234",
        },
    )
    assert r.headers.get("content-type", "").startswith("application/json")
    # Either categorised 503 or 422 (input validation); not 500.
    assert r.status_code in (200, 400, 422, 503), r.text

    # Video generate — bogus job id should return a clean 404 with
    # JSON detail, not a stack trace.
    r = await app_client.post(
        "/api/v1/video/generate",
        json={
            "job_id": "00000000-0000-0000-0000-000000000000",
            "image_artifact_id": "00000000-0000-0000-0000-000000000000",
            "audio_artifact_id": "00000000-0000-0000-0000-000000000000",
            "provider_id": "sadtalker",
            "target_duration_seconds": 15,
        },
    )
    assert r.headers.get("content-type", "").startswith("application/json")
    assert r.status_code in (200, 404, 422), r.text
