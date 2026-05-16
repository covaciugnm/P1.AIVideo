"""Phase 2 integration test — full no-op DAG end-to-end.

Verified paths:
    1. A valid job runs the full DAG and reaches `published`.
    2. `stage_runs` rows are recorded for every DAG stage.
    3. `compliance_events` rows are recorded for all four compliance gates.
    4. `pre_lipsync_auth` produces a `compliance_token` with the required claims.
    5. LipSync refuses to run without a valid `compliance_token`.
    6. A job that fails an upstream invariant ends in `rejected` and does NOT
       run any stages past the rejection point.
    7. The queue / DB payloads remain metadata-only — no binary blobs.

No model weights, no GPU libraries, no real video. SQLite + fakeredis.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test():
    """Same shape as the Phase 1 fixture, with the DAG runner config attached."""
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
        yield client, fake

    await fake.aclose()
    queue_publisher.reset_redis_client()
    # Await dispose so aiosqlite worker threads exit before the event loop
    # closes (otherwise pytest emits PytestUnhandledThreadExceptionWarning).
    await core_db.async_reset_engine()


def _valid_payload() -> dict:
    return {
        "brief": "Three calming bedtime habits for better sleep.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        # Phase 3C: voice_mode defaults to "tts" and requires script_text.
        "script_text": "Three calming bedtime habits for better sleep.",
    }


def _runner_config():
    """Return a DagRunnerConfig with a deterministic test signing key."""
    from agents.orchestrator.dag import DagRunnerConfig

    return DagRunnerConfig(
        signing_key="phase2-test-key-not-for-prod",
        allowed_lipsync_backend="sadtalker",
        token_ttl_seconds=3600,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_full_dag_publishes_valid_job(app_under_test):
    client, _ = app_under_test
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker

    r = await client.post("/jobs", json=_valid_payload())
    assert r.status_code == 201, r.text
    job = r.json()
    job_id = uuid.UUID(job["id"])
    assert job["status"] == "pending_compliance"

    runner = DagRunner(get_sessionmaker(), _runner_config())
    final_status = await runner.run(job_id)
    assert final_status.value == "published"

    r = await client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    fetched = r.json()
    assert fetched["status"] == "published"
    assert fetched["rejection_reason"] is None


async def test_all_dag_stage_runs_recorded(app_under_test):
    client, _ = app_under_test
    from agents.orchestrator.dag import DagRunner, load_stage_order
    from app.core.db import get_sessionmaker
    from app.models.stage_run import StageRun
    from common.enums import StageStatus

    r = await client.post("/jobs", json=_valid_payload())
    job_id = uuid.UUID(r.json()["id"])

    runner = DagRunner(get_sessionmaker(), _runner_config())
    await runner.run(job_id)

    expected_stages = load_stage_order()
    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(StageRun).where(StageRun.job_id == job_id).order_by(StageRun.started_at)
        )
        runs = list(result.scalars().all())

    actual_stages = [r.stage for r in runs]
    assert actual_stages == expected_stages
    assert all(r.status == StageStatus.succeeded for r in runs), [
        (r.stage, r.status) for r in runs
    ]
    # Every Phase 2 stage is a no-op.
    assert all(r.noop is True for r in runs)


async def test_four_compliance_events_recorded(app_under_test):
    client, _ = app_under_test
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.compliance import ComplianceDecisionType, ComplianceEvent

    r = await client.post("/jobs", json=_valid_payload())
    job_id = uuid.UUID(r.json()["id"])

    await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(ComplianceEvent).where(ComplianceEvent.job_id == job_id).order_by(
                ComplianceEvent.created_at
            )
        )
        events = list(result.scalars().all())

    gate_names = [e.gate for e in events]
    assert gate_names == [
        "policy_gate",
        "identity_guard",
        "pre_lipsync_auth",
        "export_disclosure_validation",
    ]
    assert all(e.decision == ComplianceDecisionType.accept for e in events)


# ---------------------------------------------------------------------------
# Compliance token
# ---------------------------------------------------------------------------


async def test_pre_lipsync_auth_mints_valid_token(app_under_test):
    """The token must verify cleanly and carry every required claim."""
    client, _ = app_under_test
    from agents.compliance_officer.compliance_token import verify_token
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.stage_run import StageRun

    r = await client.post("/jobs", json=_valid_payload())
    job_id = uuid.UUID(r.json()["id"])

    cfg = _runner_config()
    await DagRunner(get_sessionmaker(), cfg).run(job_id)

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(StageRun).where(
                StageRun.job_id == job_id,
                StageRun.stage == "pre_lipsync_auth",
            )
        )
        pre_auth_run = result.scalar_one()

    extra = pre_auth_run.extra or {}
    extra_extra = extra.get("extra", {})
    token = extra_extra.get("compliance_token")
    assert isinstance(token, str) and token.count(".") == 1

    claims = verify_token(token, cfg.signing_key, expected_job_id=str(job_id))
    assert claims.job_id == str(job_id)
    assert claims.synthetic_person_confirmed is True
    assert claims.consent_confirmed is True
    assert claims.watermark_required is True
    assert claims.c2pa_required is True
    assert claims.allowed_lipsync_backend == "sadtalker"
    assert claims.phase == "phase2_noop"
    assert claims.issued_by == "pre_lipsync_auth"
    assert claims.issued_at < claims.expires_at


async def test_lipsync_refuses_without_compliance_token():
    """LipSync must reject any state lacking a valid compliance_token."""
    from agents.lipsync.handler import run as lipsync_run
    from common.exceptions import StageRejection
    from common.schemas import ArtifactRef, DagState, StageOutput

    state = DagState(
        job_id=uuid.uuid4(),
        brief="anything",
        target_duration_seconds=30,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
    )
    # Provide upstream artifacts so the only blocker is the missing token.
    state.stage_outputs["face"] = StageOutput(
        artifacts={
            "portrait": ArtifactRef(artifact_type="image", uri=f"s3://bucket/{state.job_id}/portrait.png")
        }
    )
    state.stage_outputs["voice"] = StageOutput(
        artifacts={
            "narration": ArtifactRef(artifact_type="audio", uri=f"s3://bucket/{state.job_id}/narration.wav")
        }
    )

    with pytest.raises(StageRejection) as exc:
        await lipsync_run(state, signing_key="any", expected_backend="sadtalker")
    assert "compliance_token" in str(exc.value)


async def test_lipsync_refuses_token_with_wrong_signing_key():
    """A token signed with key A must not verify under key B."""
    from agents.compliance_officer.compliance_token import mint_token
    from agents.lipsync.handler import run as lipsync_run
    from common.exceptions import StageRejection
    from common.schemas import ArtifactRef, ComplianceTokenClaims, DagState, StageOutput

    job_id = uuid.uuid4()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    claims = ComplianceTokenClaims(
        job_id=str(job_id),
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
        allowed_lipsync_backend="sadtalker",
        issued_at=now,
        expires_at=now.replace(year=now.year + 1),
    )
    bad_token = mint_token(claims, "ATTACKER-KEY")
    state = DagState(
        job_id=job_id,
        brief="anything",
        target_duration_seconds=30,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
        compliance_token=bad_token,
    )
    state.stage_outputs["face"] = StageOutput(
        artifacts={"portrait": ArtifactRef(artifact_type="image", uri=f"s3://bucket/{job_id}/portrait.png")}
    )
    state.stage_outputs["voice"] = StageOutput(
        artifacts={
            "narration": ArtifactRef(artifact_type="audio", uri=f"s3://bucket/{job_id}/narration.wav")
        }
    )

    with pytest.raises(StageRejection):
        await lipsync_run(state, signing_key="REAL-KEY", expected_backend="sadtalker")


# ---------------------------------------------------------------------------
# Rejection paths
# ---------------------------------------------------------------------------


async def test_banned_keyword_brief_rejects_at_policy_gate(app_under_test):
    """A brief with a banned keyword must be rejected at policy_gate and
    no downstream stage may execute."""
    client, _ = app_under_test
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.stage_run import StageRun

    # We bypass the API validators by writing the job directly: the API
    # schema doesn't keyword-scan, so a borderline brief can land in the DB
    # and still be caught at the orchestrator's policy_gate.
    payload = dict(_valid_payload())
    payload["brief"] = "Vote for our candidate in the next election."
    r = await client.post("/jobs", json=payload)
    assert r.status_code == 201
    job_id = uuid.UUID(r.json()["id"])

    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "rejected"

    r = await client.get(f"/jobs/{job_id}")
    assert r.json()["status"] == "rejected"
    assert r.json()["rejection_reason"] is not None

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(StageRun).where(StageRun.job_id == job_id).order_by(StageRun.started_at)
        )
        runs = list(result.scalars().all())

    # Only policy_gate must have run; everything else stays absent.
    assert [r.stage for r in runs] == ["policy_gate"]
    assert runs[0].status.value == "rejected"


# ---------------------------------------------------------------------------
# Production Redis-consumer path
# ---------------------------------------------------------------------------


async def test_redis_consumer_path_runs_full_dag(app_under_test):
    """The production wiring (Orchestrator + Redis stream + the
    `make_job_created_handler` factory) must run the full no-op DAG when a
    `job.created` event arrives — not just the Phase 1 policy_gate path.

    This exercises the same path that runs in production: a job is created
    via the API (which publishes to Redis), the orchestrator consumes the
    event, the handler instantiates a DagRunner under the hood, and the job
    transitions all the way to `published`.
    """
    from agents.orchestrator.dag import DagRunnerConfig, load_stage_order
    from agents.orchestrator.handlers import make_job_created_handler
    from agents.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
    from app.core.db import get_sessionmaker
    from app.models.compliance import ComplianceDecisionType, ComplianceEvent
    from app.models.stage_run import StageRun
    from common.enums import StageStatus

    client, fake_redis = app_under_test

    # --- 1. POST /jobs publishes a reference event to the orchestrator stream.
    r = await client.post("/jobs", json=_valid_payload())
    assert r.status_code == 201, r.text
    job_id = uuid.UUID(r.json()["id"])
    assert await fake_redis.xlen("stage.orchestrator") == 1

    # --- 2. Wire the production handler and the orchestrator.
    config = _runner_config()
    handler = make_job_created_handler(get_sessionmaker(), config)
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

    # --- 3. The job must reach `published` (full DAG, not just policy_gate).
    r = await client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "published"
    assert r.json()["rejection_reason"] is None

    # --- 4. Every stage must have a succeeded StageRun row, in YAML order.
    expected_stages = load_stage_order()
    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(StageRun).where(StageRun.job_id == job_id).order_by(StageRun.started_at)
        )
        runs = list(result.scalars().all())
    assert [r.stage for r in runs] == expected_stages
    assert all(r.status == StageStatus.succeeded for r in runs), [
        (r.stage, r.status) for r in runs
    ]

    # --- 5. All four compliance gates must have logged accept events.
    async with sm() as session:
        result = await session.execute(
            select(ComplianceEvent).where(ComplianceEvent.job_id == job_id).order_by(
                ComplianceEvent.created_at
            )
        )
        events = list(result.scalars().all())
    gate_names = [e.gate for e in events]
    assert gate_names == [
        "policy_gate",
        "identity_guard",
        "pre_lipsync_auth",
        "export_disclosure_validation",
    ]
    assert all(e.decision == ComplianceDecisionType.accept for e in events)

    # --- 6. The compliance token must have been minted before lipsync.
    pre_auth = next(r for r in runs if r.stage == "pre_lipsync_auth")
    lipsync_run = next(r for r in runs if r.stage == "lipsync")
    token = (pre_auth.extra or {}).get("extra", {}).get("compliance_token")
    assert isinstance(token, str) and token.count(".") == 1
    assert pre_auth.started_at < lipsync_run.started_at

    # --- 7. Metadata-only invariant: every artifact value carries a uri, no bytes.
    # Phase 9B/9D widened the allowed schemes: ``placeholder://`` URIs
    # explicitly mark metadata-only stage outputs (face/editor when no
    # real media is configured) — they carry no .png/.mp4 extension and
    # no local_path, so the DAG runner can't promote them to the
    # artifacts table.
    for run in runs:
        for _key, artifact in (run.artifacts or {}).items():
            assert isinstance(artifact, dict)
            assert isinstance(artifact.get("uri"), str)
            assert artifact["uri"].startswith(("s3://", "placeholder://"))


async def test_redis_consumer_path_rejects_banned_brief(app_under_test):
    """The Redis worker path must propagate policy_gate rejection — the job
    ends in `rejected` and no downstream stage runs."""
    from agents.orchestrator.handlers import make_job_created_handler
    from agents.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
    from app.core.db import get_sessionmaker
    from app.models.stage_run import StageRun

    client, fake_redis = app_under_test
    payload = dict(_valid_payload())
    payload["brief"] = "Vote for our candidate next election."
    r = await client.post("/jobs", json=payload)
    job_id = uuid.UUID(r.json()["id"])

    handler = make_job_created_handler(get_sessionmaker(), _runner_config())
    orchestrator = Orchestrator(
        client=fake_redis,
        config=OrchestratorConfig(
            queue_topic_orchestrator="stage.orchestrator",
            block_ms=100,
        ),
        handler=handler,
    )
    await orchestrator.run_once()

    r = await client.get(f"/jobs/{job_id}")
    assert r.json()["status"] == "rejected"

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(StageRun).where(StageRun.job_id == job_id).order_by(StageRun.started_at)
        )
        runs = list(result.scalars().all())
    # Only policy_gate ran; no downstream stages.
    assert [r.stage for r in runs] == ["policy_gate"]
    assert runs[0].status.value == "rejected"


# ---------------------------------------------------------------------------
# Metadata-only invariant
# ---------------------------------------------------------------------------


async def test_queue_and_stage_runs_are_metadata_only(app_under_test):
    """Spot-check that nothing larger than reference metadata is written
    to Redis or the stage_runs table."""
    client, fake_redis = app_under_test
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.stage_run import StageRun

    r = await client.post("/jobs", json=_valid_payload())
    job_id = uuid.UUID(r.json()["id"])

    # Inspect the queue messages from the backend's publish.
    for topic in ("stage.orchestrator", "stage.compliance"):
        entries = await fake_redis.xrange(topic, "-", "+")
        assert entries, f"no message on {topic}"
        for _id, fields in entries:
            raw = fields["data"]
            # All messages must be small JSON envelopes (< 1 KB).
            assert len(raw) < 1024
            assert "brief" not in raw or len(raw) < 1024  # double belt-and-braces

    await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)

    # Inspect every stage_runs row: artifact values must be reference dicts
    # (containing a uri string), never binary.
    # Phase 9B/9D widened allowed URI schemes — see the sibling assertion
    # in test_queue_and_stage_runs_are_metadata_only for context.
    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(select(StageRun).where(StageRun.job_id == job_id))
        for row in result.scalars().all():
            for _key, artifact in (row.artifacts or {}).items():
                assert isinstance(artifact, dict)
                assert isinstance(artifact.get("uri"), str)
                assert artifact["uri"].startswith(("s3://", "placeholder://"))
