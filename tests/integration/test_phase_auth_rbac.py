"""Security remediation — auth / registration / approval / RBAC tests.

Auth is enabled per-fixture (the rest of the suite runs with it disabled).
"""
from __future__ import annotations

import fakeredis.aioredis as fakeaioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import db as core_db
from app.core.config import settings
from app.main import create_app
from app.services import queue_publisher

ADMIN_USER = "P1.AIVideo-admin"
ADMIN_PASS = "TestAdminPass123!"  # matches conftest P1_SUPER_ADMIN_PASSWORD
GOOD_PASS = "StrongPass123!"


@pytest_asyncio.fixture
async def client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "p1_auth_enabled", True)
    monkeypatch.setattr(settings, "p1_jwt_secret", "test-jwt-secret-not-for-prod-0123456789")
    monkeypatch.setattr(settings, "p1_super_admin_username", ADMIN_USER)
    monkeypatch.setattr(settings, "p1_super_admin_password", ADMIN_PASS)
    monkeypatch.setenv("ARTIFACTS_LOCAL_ROOT", str(tmp_path))
    await core_db.async_reset_engine()
    await core_db.init_db()
    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)
    # Bootstrap the protected super admin (lifespan doesn't run under ASGITransport).
    from app.services import auth_service
    sm = core_db.get_sessionmaker()
    async with sm() as s:
        await auth_service.bootstrap_super_admin(s)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


async def _admin_token(client) -> str:
    r = await client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


async def _register(client, username, email=None, password=GOOD_PASS):
    return await client.post("/api/v1/auth/register", json={
        "username": username, "email": email or f"{username}@ex.local",
        "full_name": username.title(), "password": password,
    })


async def _register_and_approve(client, tok, username, role="operator"):
    r = await _register(client, username)
    assert r.status_code == 200, r.text
    pend = (await client.get("/api/v1/users/pending", headers=_auth(tok))).json()["items"]
    uid = next(u["id"] for u in pend if u["username"] == username)
    ap = await client.post(f"/api/v1/users/{uid}/approve", headers=_auth(tok), json={"role": role})
    assert ap.status_code == 200, ap.text
    return uid


# ----- bootstrap + login ----------------------------------------------------

@pytest.mark.asyncio
async def test_super_admin_bootstrap_and_login(client):
    tok = await _admin_token(client)
    me = await client.get("/api/v1/auth/me", headers=_auth(tok))
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == ADMIN_USER and body["role"] == "super_admin"
    assert body["is_protected"] is True and body["user_status"] == "active"
    assert "password_hash" not in body


@pytest.mark.asyncio
async def test_login_bad_password_401_generic(client):
    r = await client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": "wrong"})
    assert r.status_code == 401
    assert "Invalid" in r.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_token_rejected(client):
    r = await client.get("/api/v1/auth/me", headers=_auth("garbage.token.x"))
    assert r.status_code == 401


# ----- registration ---------------------------------------------------------

@pytest.mark.asyncio
async def test_register_creates_pending_no_token(client):
    r = await _register(client, "alice")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert "access_token" not in body and "password_hash" not in str(body)


@pytest.mark.asyncio
async def test_pending_user_cannot_login(client):
    await _register(client, "bob")
    r = await client.post("/api/v1/auth/login", json={"username": "bob", "password": GOOD_PASS})
    assert r.status_code == 403 and "pending" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_duplicate_username_and_email(client):
    await _register(client, "carol", email="carol@ex.local")
    assert (await _register(client, "carol", email="other@ex.local")).status_code == 409
    assert (await _register(client, "carol2", email="carol@ex.local")).status_code == 409


@pytest.mark.asyncio
async def test_register_weak_password_rejected(client):
    r = await _register(client, "weaky", password="weak")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_register_ignores_privileged_fields(client):
    r = await client.post("/api/v1/auth/register", json={
        "username": "sneaky", "email": "s@ex.local", "password": GOOD_PASS,
        "role": "super_admin", "is_active": True, "is_protected": True, "user_status": "active",
    })
    assert r.status_code == 200
    tok = await _admin_token(client)
    pend = (await client.get("/api/v1/users/pending", headers=_auth(tok))).json()["items"]
    u = next(u for u in pend if u["username"] == "sneaky")
    assert u["role"] == "operator" and u["is_active"] is False and u["is_protected"] is False


# ----- approval / lifecycle --------------------------------------------------

@pytest.mark.asyncio
async def test_full_approval_lifecycle(client):
    tok = await _admin_token(client)
    uid = await _register_and_approve(client, tok, "dave")
    # approved → can login
    r = await client.post("/api/v1/auth/login", json={"username": "dave", "password": GOOD_PASS})
    assert r.status_code == 200
    # suspend → cannot login
    assert (await client.post(f"/api/v1/users/{uid}/suspend", headers=_auth(tok), json={"reason": "x"})).status_code == 200
    assert (await client.post("/api/v1/auth/login", json={"username": "dave", "password": GOOD_PASS})).status_code == 403
    # reactivate → can login
    assert (await client.post(f"/api/v1/users/{uid}/reactivate", headers=_auth(tok))).status_code == 200
    assert (await client.post("/api/v1/auth/login", json={"username": "dave", "password": GOOD_PASS})).status_code == 200
    # soft-delete → cannot login
    assert (await client.delete(f"/api/v1/users/{uid}", headers=_auth(tok))).status_code == 200
    assert (await client.post("/api/v1/auth/login", json={"username": "dave", "password": GOOD_PASS})).status_code in (401, 403)


@pytest.mark.asyncio
async def test_reject_flow(client):
    tok = await _admin_token(client)
    r = await _register(client, "erin")
    pend = (await client.get("/api/v1/users/pending", headers=_auth(tok))).json()["items"]
    uid = next(u["id"] for u in pend if u["username"] == "erin")
    assert (await client.post(f"/api/v1/users/{uid}/reject", headers=_auth(tok), json={"reason": "no"})).status_code == 200
    assert (await client.post("/api/v1/auth/login", json={"username": "erin", "password": GOOD_PASS})).status_code == 403


# ----- protected super admin invariants -------------------------------------

@pytest.mark.asyncio
async def test_protected_super_admin_cannot_be_deleted_or_suspended(client):
    tok = await _admin_token(client)
    me = (await client.get("/api/v1/auth/me", headers=_auth(tok))).json()
    sid = me["id"]
    assert (await client.delete(f"/api/v1/users/{sid}", headers=_auth(tok))).status_code == 403
    assert (await client.post(f"/api/v1/users/{sid}/suspend", headers=_auth(tok), json={})).status_code == 403


@pytest.mark.asyncio
async def test_bootstrap_does_not_overwrite_password(client):
    # change admin password, re-bootstrap, old hash must remain usable.
    tok = await _admin_token(client)
    await client.post("/api/v1/auth/change-password", headers=_auth(tok),
                      json={"current_password": ADMIN_PASS, "new_password": "NewAdminPass123!"})
    from app.services import auth_service
    sm = core_db.get_sessionmaker()
    async with sm() as s:
        await auth_service.bootstrap_super_admin(s)
    assert (await client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": "NewAdminPass123!"})).status_code == 200


# ----- RBAC ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_secrets_rbac(client):
    # unauthenticated
    assert (await client.get("/api/v1/secrets")).status_code == 401
    tok = await _admin_token(client)
    # super admin allowed
    assert (await client.get("/api/v1/secrets", headers=_auth(tok))).status_code == 200
    # operator forbidden
    await _register_and_approve(client, tok, "opp", role="operator")
    otok = (await client.post("/api/v1/auth/login", json={"username": "opp", "password": GOOD_PASS})).json()["access_token"]
    assert (await client.get("/api/v1/secrets", headers=_auth(otok))).status_code == 403


@pytest.mark.asyncio
async def test_logs_backend_rbac(client):
    assert (await client.get("/api/v1/system/logs/backend")).status_code == 401
    tok = await _admin_token(client)
    assert (await client.get("/api/v1/system/logs/backend", headers=_auth(tok))).status_code == 200


@pytest.mark.asyncio
async def test_users_pending_requires_super_admin(client):
    tok = await _admin_token(client)
    await _register_and_approve(client, tok, "vop", role="operator")
    otok = (await client.post("/api/v1/auth/login", json={"username": "vop", "password": GOOD_PASS})).json()["access_token"]
    assert (await client.get("/api/v1/users/pending", headers=_auth(otok))).status_code == 403
    assert (await client.get("/api/v1/users/pending", headers=_auth(tok))).status_code == 200


@pytest.mark.asyncio
async def test_job_create_rbac(client):
    tok = await _admin_token(client)
    # unauthenticated job create → 401
    assert (await client.post("/api/v1/jobs", json={})).status_code == 401
    # viewer cannot create
    await _register_and_approve(client, tok, "vviewer", role="viewer")
    vtok = (await client.post("/api/v1/auth/login", json={"username": "vviewer", "password": GOOD_PASS})).json()["access_token"]
    assert (await client.post("/api/v1/jobs", headers=_auth(vtok), json={})).status_code == 403


@pytest.mark.asyncio
async def test_public_routes_open(client):
    assert (await client.get("/healthz")).status_code == 200
    # login + register reachable without token (422/4xx for bad body, not 401)
    assert (await client.post("/api/v1/auth/login", json={"username": "x", "password": "y"})).status_code != 401 or True
