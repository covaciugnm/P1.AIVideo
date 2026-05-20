"""Security audit logging tests — persistent SecurityAuditEvent + endpoint."""
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
ADMIN_PASS = "TestAdminPass123!"
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


def _auth(t): return {"Authorization": f"Bearer {t}"}


async def _admin_token(client):
    r = await client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    return r.json()["access_token"]


async def _events(client, tok, event_type=None):
    qs = f"?event_type={event_type}" if event_type else ""
    r = await client.get(f"/api/v1/audit/security-events{qs}", headers=_auth(tok))
    assert r.status_code == 200, r.text
    return r.json()["items"]


@pytest.mark.asyncio
async def test_request_id_header_present(client):
    r = await client.get("/healthz")
    assert r.headers.get("X-Request-ID")


@pytest.mark.asyncio
async def test_login_failed_and_success_logged(client):
    await client.post("/api/v1/auth/login", json={"username": "nobody", "password": "WrongPass123!"})
    tok = await _admin_token(client)
    failed = await _events(client, tok, "LOGIN_FAILED")
    assert any(e["result"] == "failed" for e in failed)
    # the failed event must NOT leak a password anywhere
    blob = str(failed)
    assert "WrongPass123!" not in blob
    success = await _events(client, tok, "LOGIN_SUCCESS")
    assert any(e["actor_username"] == ADMIN_USER for e in success)
    # request_id recorded
    assert success[0]["request_id"]


@pytest.mark.asyncio
async def test_register_logged(client):
    await client.post("/api/v1/auth/register", json={
        "username": "log-test", "email": "lt@ex.local", "password": GOOD_PASS})
    tok = await _admin_token(client)
    ev = await _events(client, tok, "REGISTER_CREATED_PENDING")
    assert any(e["actor_username"] == "log-test" for e in ev)
    assert GOOD_PASS not in str(ev)


@pytest.mark.asyncio
async def test_login_pending_blocked_logged(client):
    await client.post("/api/v1/auth/register", json={
        "username": "pend", "email": "p@ex.local", "password": GOOD_PASS})
    await client.post("/api/v1/auth/login", json={"username": "pend", "password": GOOD_PASS})
    tok = await _admin_token(client)
    ev = await _events(client, tok, "LOGIN_BLOCKED_PENDING")
    assert any(e["result"] == "blocked" for e in ev)


@pytest.mark.asyncio
async def test_user_admin_actions_logged(client):
    tok = await _admin_token(client)
    await client.post("/api/v1/auth/register", json={
        "username": "appr", "email": "a@ex.local", "password": GOOD_PASS})
    pend = (await client.get("/api/v1/users/pending", headers=_auth(tok))).json()["items"]
    uid = next(u["id"] for u in pend if u["username"] == "appr")
    await client.post(f"/api/v1/users/{uid}/approve", headers=_auth(tok), json={"role": "operator"})
    await client.post(f"/api/v1/users/{uid}/suspend", headers=_auth(tok), json={})
    appr = await _events(client, tok, "USER_APPROVED")
    assert any(e["actor_username"] == ADMIN_USER and e["target_id"] == uid for e in appr)
    assert any(e["metadata_json"].get("new_status") == "active" for e in appr)
    assert await _events(client, tok, "USER_SUSPENDED")


@pytest.mark.asyncio
async def test_protected_super_admin_block_logged(client):
    tok = await _admin_token(client)
    sid = (await client.get("/api/v1/auth/me", headers=_auth(tok))).json()["id"]
    await client.delete(f"/api/v1/users/{sid}", headers=_auth(tok))
    ev = await _events(client, tok, "PROTECTED_SUPER_ADMIN_MODIFICATION_BLOCKED")
    assert any(e["result"] == "blocked" for e in ev)


@pytest.mark.asyncio
async def test_secret_access_logged(client):
    tok = await _admin_token(client)
    await client.get("/api/v1/secrets", headers=_auth(tok))
    assert await _events(client, tok, "SECRET_LIST_VIEWED")
    # operator denied
    await client.post("/api/v1/auth/register", json={
        "username": "denyop", "email": "d@ex.local", "password": GOOD_PASS})
    pend = (await client.get("/api/v1/users/pending", headers=_auth(tok))).json()["items"]
    uid = next(u["id"] for u in pend if u["username"] == "denyop")
    await client.post(f"/api/v1/users/{uid}/approve", headers=_auth(tok), json={"role": "operator"})
    otok = (await client.post("/api/v1/auth/login", json={"username": "denyop", "password": GOOD_PASS})).json()["access_token"]
    await client.get("/api/v1/secrets", headers=_auth(otok))
    assert await _events(client, tok, "SECRET_ACCESS_DENIED")


@pytest.mark.asyncio
async def test_backend_logs_access_logged(client):
    tok = await _admin_token(client)
    await client.get("/api/v1/system/logs/backend", headers=_auth(tok))
    assert await _events(client, tok, "BACKEND_LOGS_VIEWED")


@pytest.mark.asyncio
async def test_audit_endpoint_requires_super_admin(client):
    assert (await client.get("/api/v1/audit/security-events")).status_code == 401
