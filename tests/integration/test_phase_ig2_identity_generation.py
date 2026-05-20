"""Phase IG-2 — identity prompt builder, VRAM-aware selection, and the
generate-initial / generate-consistent endpoints (validation paths).

The provider dispatch itself needs a live ComfyUI, so these tests cover
the pure logic + the guards that fire BEFORE any network call.
"""
from __future__ import annotations

import fakeredis.aioredis as fakeaioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import db as core_db
from app.main import create_app
from app.services import queue_publisher
from app.services.character_prompt_builder import (
    SceneParams,
    build_consistent_prompt,
    build_initial_prompt,
)
from app.services.image_workflow_select import select_workflow


# ----- prompt builder (pure) ------------------------------------------------

_PROFILE = {
    "identity": {"name": "Test", "gender": "female", "age": 30, "is_public_persona": False},
    "appearance": {
        "skin_tone": "fair", "hair_color": "auburn", "eye_color": "green",
        "face_shape": "oval", "negative_visual_constraints": "no tattoos",
    },
    "script_behaviour": {"default_camera_framing": "medium shot"},
}


def test_identity_block_present_in_both_modes():
    pos_i, neg_i = build_initial_prompt(_PROFILE)
    assert "IDENTITY LOCK" in pos_i
    pos_c, neg_c = build_consistent_prompt(
        _PROFILE, SceneParams(scene_prompt="in an autumn park", outfit_prompt="red coat")
    )
    assert "IDENTITY LOCK" in pos_c
    assert "SCENE:" in pos_c and "STYLE:" in pos_c
    assert "REFERENCE USAGE" in pos_c


def test_scene_traits_only_in_consistent_prompt():
    pos, _ = build_consistent_prompt(
        _PROFILE, SceneParams(scene_prompt="walking on a beach", outfit_prompt="linen shirt")
    )
    assert "walking on a beach" in pos
    assert "linen shirt" in pos


def test_negative_always_protects_identity_and_compliance():
    _, neg = build_consistent_prompt(_PROFILE, SceneParams())
    assert "different person" in neg
    assert "real person" in neg  # compliance negative
    assert "no tattoos" in neg   # character's own constraint


# ----- VRAM-aware selection -------------------------------------------------

def test_select_fallback_on_small_vram(monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER_DEFAULT", "auto")
    monkeypatch.setenv("IMAGE_GPU_VRAM_GB_OVERRIDE", "24")
    sel = select_workflow("consistent")
    assert sel.tier == "fallback"
    assert sel.workflow_name == "sdxl_instantid_consistent"


def test_select_primary_on_big_vram(monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER_DEFAULT", "auto")
    monkeypatch.setenv("IMAGE_GPU_VRAM_GB_OVERRIDE", "128")
    sel = select_workflow("consistent")
    assert sel.tier == "primary"
    assert sel.workflow_name == "pulid_flux_consistent"


def test_select_pinned_overrides_vram(monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER_DEFAULT", "sdxl_instantid")
    monkeypatch.setenv("IMAGE_GPU_VRAM_GB_OVERRIDE", "128")
    assert select_workflow("consistent").tier == "fallback"


def test_select_no_gpu_defaults_to_fallback(monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER_DEFAULT", "auto")
    monkeypatch.setenv("IMAGE_GPU_VRAM_GB_OVERRIDE", "")
    monkeypatch.setattr(
        "app.services.image_workflow_select.detect_total_vram_gb", lambda: None
    )
    assert select_workflow("initial").tier == "fallback"


# ----- endpoint guards ------------------------------------------------------

@pytest_asyncio.fixture
async def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path))
    await core_db.async_reset_engine()
    await core_db.init_db()
    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


def _profile(name, real_person=False):
    ident = {"name": name, "gender": "female", "is_public_persona": True,
             "spoken_languages": ["ro"]}
    if real_person:
        ident["is_real_person"] = True
    return {
        "identity": ident,
        "appearance": {}, "education": {"certifications": [], "previous_roles": [], "expertise": []},
        "personality": {}, "voice": {}, "script_behaviour": {"allowed_topics": [], "blocked_topics": []},
    }


async def _create(client, name, real_person=False):
    r = await client.post("/api/v1/characters", json={"profile": _profile(name, real_person), "status": "editing"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_consistent_without_references_rejected(client):
    c = await _create(client, "NoRefs")
    r = await client.post(
        f"/api/v1/characters/{c['id']}/images/generate-consistent",
        json={"scene_prompt": "in an office"},
    )
    assert r.status_code == 422, r.text
    assert "canonical" in r.text.lower()


@pytest.mark.asyncio
async def test_real_person_rejected_synthetic_only(client, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_ONLY_ENFORCED", "true")
    c = await _create(client, "RealPerson", real_person=True)
    r = await client.post(
        f"/api/v1/characters/{c['id']}/images/generate-initial",
        json={"aspect_ratio": "portrait"},
    )
    assert r.status_code == 422, r.text
    assert "real" in r.text.lower()


@pytest.mark.asyncio
async def test_public_persona_synthetic_is_allowed(client, monkeypatch):
    # is_public_persona=true must NOT block generation (synthetic personas
    # appear publicly by design). It will fail later on the provider, not here.
    monkeypatch.setenv("SYNTHETIC_ONLY_ENFORCED", "true")
    c = await _create(client, "PublicSynthetic", real_person=False)
    r = await client.post(
        f"/api/v1/characters/{c['id']}/images/generate-initial",
        json={"aspect_ratio": "portrait"},
    )
    # Not a synthetic-only rejection (will be a provider error instead).
    assert "synthetic-only" not in r.text.lower()
    assert "real person" not in r.text.lower()
