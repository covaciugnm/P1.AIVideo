"""Phase 6D — provider registry hardening.

Pins the multi-category provider catalog so the operator/UI surface
stays stable as new providers land. Highlights:

- All five categories exist on the top-level catalog.
- Each ProviderInfo carries the Phase 6D fields (requires_gpu, etc.).
- GPU placeholders advertise requires_gpu=True.
- Secrets in env never appear in any response body.
- Unknown provider lookup returns a structured 404.
- ProviderSelection accepts audio_processor_id + image_processor_id.
- Loading the registry / API module never pulls in heavy/ML deps.
"""
from __future__ import annotations

import subprocess
import sys
import uuid

import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


_REQUIRED_PROVIDER_FIELDS = {
    "category",
    "provider_id",
    "label",
    "backend_type",
    "default_model",
    "is_local",
    "status",
    "notes",
    "local_or_external",
    "supported_models",
    "requires_network",
    "requires_gpu",
    "requires_model_files",
    "healthcheck_available",
    "warning",
    "docs_url",
    "is_custom",
}


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_AUDIO_ROOT", str(tmp_path / "audio"))
    monkeypatch.setenv("UPLOAD_IMAGE_ROOT", str(tmp_path / "images"))
    monkeypatch.setenv("UPLOAD_TEXT_ROOT", str(tmp_path / "text"))
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")
    monkeypatch.delenv("SCRIPTWRITER_ENABLE_NETWORK_CALLS", raising=False)

    from app.core import db as core_db
    from app.main import create_app
    from app.services import queue_publisher

    await core_db.async_reset_engine()
    await core_db.init_db()
    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


# ---------------------------------------------------------------------------
# Catalog shape
# ---------------------------------------------------------------------------


async def test_catalog_has_all_five_categories(app_under_test):
    r = await app_under_test.get("/api/v1/providers")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "llm",
        "tts",
        "video_generator",
        "audio_processor",
        "image_processor",
    }
    for category, entries in body.items():
        assert len(entries) >= 1, f"category {category} is empty"


async def test_every_provider_record_has_required_fields(app_under_test):
    r = await app_under_test.get("/api/v1/providers")
    body = r.json()
    for category, entries in body.items():
        for p in entries:
            missing = _REQUIRED_PROVIDER_FIELDS - set(p.keys())
            assert not missing, f"{category}/{p.get('provider_id')} missing: {missing}"


# ---------------------------------------------------------------------------
# Per-category endpoints
# ---------------------------------------------------------------------------


async def test_per_category_endpoints_each_return_list(app_under_test):
    for path in (
        "/api/v1/providers/llm",
        "/api/v1/providers/tts",
        "/api/v1/providers/video-generators",
        "/api/v1/providers/audio-processors",
        "/api/v1/providers/image-processors",
    ):
        r = await app_under_test.get(path)
        assert r.status_code == 200, (path, r.text)
        body = r.json()
        assert isinstance(body, list)
        assert len(body) >= 1


# ---------------------------------------------------------------------------
# Category-specific expectations
# ---------------------------------------------------------------------------


async def test_audio_processors_include_ffmpeg_convert(app_under_test):
    r = await app_under_test.get("/api/v1/providers/audio-processors")
    ids = {p["provider_id"] for p in r.json()}
    assert "ffmpeg_convert" in ids


async def test_image_processors_include_stdlib_image_validation(app_under_test):
    r = await app_under_test.get("/api/v1/providers/image-processors")
    rows = r.json()
    ids = {p["provider_id"] for p in rows}
    assert "stdlib_image_validation" in ids
    stdlib = next(p for p in rows if p["provider_id"] == "stdlib_image_validation")
    assert stdlib["status"] == "available"


async def test_video_gpu_placeholders_advertise_requires_gpu(app_under_test):
    r = await app_under_test.get("/api/v1/providers/video-generators")
    by_id = {p["provider_id"]: p for p in r.json()}
    for vid_id in ("sadtalker", "musetalk", "wav2lip", "liveportrait"):
        assert by_id[vid_id]["requires_gpu"] is True, vid_id
    # External + local-http stubs don't require a GPU directly.
    assert by_id["local_http_video"]["requires_gpu"] is False
    assert by_id["external_video_api"]["requires_gpu"] is False
    assert by_id["external_video_api"]["local_or_external"] == "external"


async def test_llm_external_providers_marked_external(app_under_test):
    r = await app_under_test.get("/api/v1/providers/llm")
    by_id = {p["provider_id"]: p for p in r.json()}
    for pid in ("openai", "anthropic", "openai_compatible"):
        if pid in by_id:
            assert by_id[pid]["local_or_external"] == "external", pid


# ---------------------------------------------------------------------------
# Secrets safety
# ---------------------------------------------------------------------------


async def test_catalog_does_not_leak_api_keys(app_under_test, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-phase6d-secret-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-phase6d-secret-anthropic")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-phase6d-compat")
    r = await app_under_test.get("/api/v1/providers")
    text = r.text
    assert "sk-phase6d-secret-openai" not in text
    assert "sk-phase6d-secret-anthropic" not in text
    assert "sk-phase6d-compat" not in text


async def test_catalog_does_not_leak_endpoint_credentials(app_under_test, monkeypatch):
    """Even with a credential-looking endpoint URL, no Authorization /
    token text appears in any provider record."""
    monkeypatch.setenv("LOCAL_LLM_URL", "https://user:token-secret@some.host/v1")
    r = await app_under_test.get("/api/v1/providers/llm")
    assert "token-secret" not in r.text


# ---------------------------------------------------------------------------
# Per-provider lookup
# ---------------------------------------------------------------------------


async def test_provider_detail_endpoint_returns_known_provider(app_under_test):
    r = await app_under_test.get("/api/v1/providers/llm/template")
    assert r.status_code == 200
    body = r.json()
    assert body["provider_id"] == "template"
    assert body["category"] == "llm"
    assert body["status"] == "available"


async def test_provider_detail_supports_dash_and_underscore_categories(app_under_test):
    for category_slug in ("video-generators", "video_generator"):
        r = await app_under_test.get(f"/api/v1/providers/{category_slug}/sadtalker")
        assert r.status_code == 200, (category_slug, r.text)
        assert r.json()["provider_id"] == "sadtalker"


async def test_provider_detail_unknown_category_returns_404(app_under_test):
    r = await app_under_test.get("/api/v1/providers/not_a_category/template")
    assert r.status_code == 404
    assert "unknown category" in r.json()["detail"]


async def test_provider_detail_unknown_provider_returns_404(app_under_test):
    r = await app_under_test.get("/api/v1/providers/llm/not_a_provider")
    assert r.status_code == 404
    assert "unknown provider" in r.json()["detail"]


# ---------------------------------------------------------------------------
# ProviderSelection round-trip with new categories
# ---------------------------------------------------------------------------


def _create_payload(provider_selection: dict | None = None) -> dict:
    return {
        "brief": "phase 6d",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "script_text": "hello",
        **({"provider_selection": provider_selection} if provider_selection else {}),
    }


async def test_job_provider_selection_accepts_audio_and_image_processor_ids(app_under_test):
    sel = {
        "script_provider_id": "template",
        "tts_provider_id": "piper",
        "video_provider_id": "sadtalker",
        "audio_processor_id": "ffmpeg_convert",
        "image_processor_id": "stdlib_image_validation",
    }
    r = await app_under_test.post("/api/v1/jobs", json=_create_payload(sel))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["provider_selection"] == sel


async def test_job_provider_selection_accepts_future_unknown_ids(app_under_test):
    """Unknown provider IDs are accepted at write time. The runtime is
    the gate; jobs can carry forward-looking IDs for future-phase
    runtimes."""
    sel = {
        "tts_provider_id": "some_unknown_future_tts",
        "audio_processor_id": "future_denoise",
    }
    r = await app_under_test.post("/api/v1/jobs", json=_create_payload(sel))
    assert r.status_code == 201, r.text
    assert r.json()["provider_selection"]["tts_provider_id"] == "some_unknown_future_tts"
    assert r.json()["provider_selection"]["audio_processor_id"] == "future_denoise"


async def test_job_provider_selection_rejects_unknown_field(app_under_test):
    sel = {"unknown_field": "x"}
    r = await app_under_test.post("/api/v1/jobs", json=_create_payload(sel))
    assert r.status_code == 422


async def test_job_patch_can_update_audio_and_image_processor(app_under_test):
    create = await app_under_test.post("/api/v1/jobs", json=_create_payload())
    job_id = create.json()["id"]

    r = await app_under_test.patch(
        f"/api/v1/jobs/{job_id}",
        json={
            "provider_selection": {
                "audio_processor_id": "ffmpeg_convert",
                "image_processor_id": "stdlib_image_validation",
            }
        },
    )
    assert r.status_code == 200, r.text
    ps = r.json()["provider_selection"]
    assert ps["audio_processor_id"] == "ffmpeg_convert"
    assert ps["image_processor_id"] == "stdlib_image_validation"


# ---------------------------------------------------------------------------
# Import safety — registry must not pull in heavy ML / network deps
# ---------------------------------------------------------------------------


_FORBIDDEN = (
    "torch",
    "torchvision",
    "torchaudio",
    "diffusers",
    "transformers",
    "accelerate",
    "openai",
    "anthropic",
    "httpx",
    "aiohttp",
    "sadtalker",
    "musetalk",
    "wav2lip",
    "liveportrait",
    "piper",
)


def test_registry_module_loads_without_heavy_deps():
    code = (
        "import sys, app.services.provider_registry; "
        f"print([m for m in {_FORBIDDEN!r} if m in sys.modules])"
    )
    res = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=20
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "[]", (
        f"forbidden imports leaked at registry load: {res.stdout.strip()}"
    )


def test_providers_api_module_loads_without_heavy_deps():
    code = (
        "import sys, app.api.providers; "
        f"print([m for m in {_FORBIDDEN!r} if m in sys.modules])"
    )
    res = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=20
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "[]"


# ---------------------------------------------------------------------------
# Defensive: registry helpers behave as documented
# ---------------------------------------------------------------------------


def test_registry_get_provider_returns_none_for_unknown():
    from app.services import provider_registry

    assert provider_registry.get_provider("llm", "does_not_exist") is None
    assert provider_registry.get_provider("not_a_category", "template") is None
    assert provider_registry.list_providers_by_category("not_a_category") == []


def test_registry_get_provider_returns_record_for_known():
    from app.services import provider_registry

    info = provider_registry.get_provider("audio_processor", "ffmpeg_convert")
    assert info is not None
    assert info.provider_id == "ffmpeg_convert"
    assert info.category == "audio_processor"


_ = uuid  # keep the import even if a future test removes the only use site
