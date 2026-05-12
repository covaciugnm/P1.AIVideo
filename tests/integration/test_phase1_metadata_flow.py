"""Phase 1 integration test: end-to-end metadata flow.

Verified path:
    POST /jobs (valid payload)
    → Job row written to SQLite
    → job.created event published to fakeredis on the orchestrator + compliance streams
    → Orchestrator.run_once() consumes the event
    → handle_job_created runs policy_gate against the brief
    → Job status moves to `accepted` (or `rejected` for the banned-keyword case)

No model weights, no GPU libraries, no real video generation. SQLite + fakeredis
keep the test self-contained.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app_under_test():
    """Bring up a fresh app instance with SQLite + fakeredis wired in."""
    # Import inside the fixture so the conftest env vars are honored.
    from app.core import db as core_db
    from app.main import create_app
    from app.services import queue_publisher

    # Force a clean engine for each test (SQLite :memory: is per-connection,
    # so we must reuse the same engine for the whole test).
    core_db.reset_engine()
    await core_db.init_db()

    # Patch queue publisher with fakeredis so xadd is captured locally.
    fake = fakeaioredis.FakeRedis(decode_responses=True)
    queue_publisher.set_redis_client(fake)

    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake

    await fake.aclose()
    queue_publisher.reset_redis_client()
    core_db.reset_engine()


async def test_healthz(app_under_test):
    client, _ = app_under_test
    r = await client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["scope"] == "metadata-only"


async def test_valid_job_reaches_accepted(app_under_test):
    client, fake_redis = app_under_test
    from agents.orchestrator.handlers import make_job_created_handler
    from agents.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
    from app.core.db import get_sessionmaker

    # 1. Create the job.
    payload = {
        "brief": "Three calming bedtime habits for better sleep.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
    }
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 201, r.text
    job = r.json()
    job_id = job["id"]
    assert job["status"] == "pending_compliance"

    # 2. Both streams got a message — reference only, no media payload.
    assert await fake_redis.xlen("stage.orchestrator") == 1
    assert await fake_redis.xlen("stage.compliance") == 1

    # 3. Orchestrator picks up the event and runs the policy gate.
    handler = make_job_created_handler(get_sessionmaker())
    orchestrator = Orchestrator(
        client=fake_redis,
        config=OrchestratorConfig(
            queue_topic_orchestrator="stage.orchestrator",
            block_ms=100,
        ),
        handler=handler,
    )
    processed = await orchestrator.run_once()
    assert processed == 1

    # 4. Job is accepted.
    r = await client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    fetched = r.json()
    assert fetched["status"] == "accepted"
    assert fetched["rejection_reason"] is None


async def test_invalid_payload_rejected_at_api(app_under_test):
    client, _ = app_under_test

    # consent_confirmed=False — must fail at the API schema layer (422).
    payload = {
        "brief": "A simple educational reel.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": False,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
    }
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422


async def test_out_of_range_duration_rejected_at_api(app_under_test):
    client, _ = app_under_test
    payload = {
        "brief": "A simple educational reel.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 5,  # below MIN_REEL_DURATION_SECONDS=15
        "watermark_required": True,
        "c2pa_required": True,
    }
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 422


async def test_policy_gate_rejects_banned_keyword():
    """The orchestrator-side gate must also reject banned content even if
    something slipped past the API schema (defense in depth)."""
    from agents.compliance_officer.policy_gate import JobBriefView, policy_gate

    view = JobBriefView(
        job_id="00000000-0000-0000-0000-000000000000",
        brief="Why you should vote for our candidate next election.",
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
    )
    decision = policy_gate(view)
    assert decision.accepted is False
    assert any("banned keyword" in reason for reason in decision.reasons)


async def test_policy_gate_rejects_missing_consent():
    """Structural rejection: gate flags it even if the API didn't see it."""
    from agents.compliance_officer.policy_gate import JobBriefView, policy_gate

    view = JobBriefView(
        job_id="00000000-0000-0000-0000-000000000000",
        brief="Three tips for cooking pasta.",
        synthetic_person_confirmed=True,
        consent_confirmed=False,  # missing consent
        watermark_required=True,
        c2pa_required=True,
    )
    decision = policy_gate(view)
    assert decision.accepted is False
    assert any("consent_confirmed" in reason for reason in decision.reasons)


async def test_compliance_event_row_recorded(app_under_test):
    """Verify a policy_gate row lands in compliance_events for audit."""
    from sqlalchemy import select

    from agents.orchestrator.handlers import make_job_created_handler
    from agents.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
    from app.core.db import get_sessionmaker
    from app.models.compliance import ComplianceDecisionType, ComplianceEvent

    client, fake_redis = app_under_test
    payload = {
        "brief": "Three calming bedtime habits for better sleep.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
    }
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 201

    handler = make_job_created_handler(get_sessionmaker())
    orchestrator = Orchestrator(
        client=fake_redis,
        config=OrchestratorConfig(
            queue_topic_orchestrator="stage.orchestrator",
            block_ms=100,
        ),
        handler=handler,
    )
    await orchestrator.run_once()

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(select(ComplianceEvent))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].gate == "policy_gate"
        assert rows[0].decision == ComplianceDecisionType.accept
        assert rows[0].reasons == []
