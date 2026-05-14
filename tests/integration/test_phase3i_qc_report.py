"""Phase 3I integration tests — QC contract + structured report artifact.

What we verify:

QC handler — direct calls:
- Happy path produces a ``QCReport`` artifact with ``ArtifactType.metadata``,
  ``application/json`` mime, content checksum, and ``passed=True`` when
  every check passes.
- Each individual check fails as expected when the corresponding
  upstream invariant is broken (incomplete segments, total duration
  mismatch, reel_draft with a local_path).
- Missing required artifacts (edit_plan, reel_draft, script) raise
  ``StageRejection`` — structural wiring failures, not content
  failures.

End-to-end through the DAG:
- A valid job produces a metadata-type artifact whose
  ``metadata_json["qc_report"]`` matches the structured ``QCReport``
  shape, ``qc_passed=true``, and back-references the upstream script
  + edit_plan + reel_draft URIs.

Import discipline:
- Importing ``agents.qc.handler`` does NOT pull in ``ffmpeg``,
  ``ffprobe``, ``mediainfo``, ``moviepy``, ``cv2``, ``imageio``,
  ``numpy``, ``PIL``, ``torch``, ``diffusers``, or ``transformers``.

Boundaries:
- No real media is read; checks operate only on artifact metadata.
- No new dependencies are added.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeaioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state_with_full_upstream(
    *,
    job_id: uuid.UUID,
    target: int = 30,
    edit_plan_segments: list[dict] | None = None,
    omit_edit_plan: bool = False,
    omit_reel_draft: bool = False,
    omit_script: bool = False,
    reel_draft_local_path: str | None = None,
):
    """Construct a DagState with scriptwriter + lipsync + editor outputs."""
    from common.schemas import ArtifactRef, DagState, StageOutput

    state = DagState(
        job_id=job_id,
        brief="Bedtime tips",
        target_duration_seconds=target,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=True,
        c2pa_required=True,
    )

    # scriptwriter
    if not omit_script:
        state.stage_outputs["scriptwriter"] = StageOutput(
            artifacts={
                "script": ArtifactRef(
                    artifact_type="script",
                    uri=f"s3://bucket/{job_id}/script.json",
                    mime_type="application/json",
                    checksum_sha256="aa" * 32,
                    size_bytes=42,
                    extra={
                        "structured_script": {
                            "hook": "Hook line.",
                            "body": "Body text.",
                            "cta": "Follow for more.",
                            "full_script": "Hook line.\n\nBody text.\n\nFollow for more.",
                        }
                    },
                )
            }
        )

    # lipsync — editor needs this; qc doesn't care directly
    state.stage_outputs["lipsync"] = StageOutput(
        artifacts={
            "talking_head": ArtifactRef(
                artifact_type="video",
                uri=f"s3://bucket/{job_id}/talking_head.mp4",
            )
        }
    )

    # editor
    editor_artifacts = {}
    if not omit_edit_plan:
        # Use the user-supplied segments, or default to a Phase-3H-shaped
        # 20/65/15 split over `target` seconds.
        if edit_plan_segments is None:
            target_ms = target * 1000
            hook_ms = round(target_ms * 0.20)
            cta_ms = round(target_ms * 0.15)
            body_ms = target_ms - hook_ms - cta_ms
            edit_plan_segments = [
                {
                    "segment_type": "hook",
                    "start_seconds": 0.0,
                    "end_seconds": hook_ms / 1000.0,
                    "duration_seconds": hook_ms / 1000.0,
                    "text": "Hook line.",
                    "metadata": {},
                },
                {
                    "segment_type": "body",
                    "start_seconds": hook_ms / 1000.0,
                    "end_seconds": (hook_ms + body_ms) / 1000.0,
                    "duration_seconds": body_ms / 1000.0,
                    "text": "Body text.",
                    "metadata": {},
                },
                {
                    "segment_type": "cta",
                    "start_seconds": (hook_ms + body_ms) / 1000.0,
                    "end_seconds": (hook_ms + body_ms + cta_ms) / 1000.0,
                    "duration_seconds": cta_ms / 1000.0,
                    "text": "Follow for more.",
                    "metadata": {},
                },
            ]
        editor_artifacts["edit_plan"] = ArtifactRef(
            artifact_type="edit_plan",
            uri=f"s3://bucket/{job_id}/edit_plan.json",
            mime_type="application/json",
            checksum_sha256="bb" * 32,
            size_bytes=64,
            duration_seconds=float(target),
            extra={
                "edit_plan": {
                    "target_duration_seconds": float(target),
                    "segments": edit_plan_segments,
                    "source_script_uri": f"s3://bucket/{job_id}/script.json",
                    "source_script_checksum": "aa" * 32,
                    "metadata": {},
                },
                "phase": "phase3h",
            },
        )
    if not omit_reel_draft:
        editor_artifacts["reel_draft"] = ArtifactRef(
            artifact_type="video",
            uri=f"s3://bucket/{job_id}/reel_draft.mp4",
            local_path=reel_draft_local_path,
            extra={"phase": "phase3h_stub"},
        )
    state.stage_outputs["editor"] = StageOutput(artifacts=editor_artifacts)

    return state


# ---------------------------------------------------------------------------
# Direct handler tests — happy path
# ---------------------------------------------------------------------------


async def test_qc_emits_metadata_artifact_with_passing_report():
    from agents.qc.handler import run as qc_run
    from common.enums import ArtifactType

    state = _make_state_with_full_upstream(job_id=uuid.uuid4(), target=30)
    output = await qc_run(state)

    assert "qc_report" in output.artifacts
    ref = output.artifacts["qc_report"]
    assert ref.artifact_type == ArtifactType.metadata.value
    assert ref.mime_type == "application/json"
    assert ref.checksum_sha256 and len(ref.checksum_sha256) == 64
    assert ref.size_bytes and ref.size_bytes > 0

    report = ref.extra["qc_report"]
    assert report["passed"] is True
    assert len(report["checks"]) == 4
    assert all(c["decision"] == "pass" for c in report["checks"])
    assert report["segment_count"] == 3
    assert report["expected_segments"] == ["hook", "body", "cta"]
    assert report["target_duration_seconds"] == pytest.approx(30.0)
    # Back-references to source artifacts
    assert report["script_artifact_uri"].endswith("script.json")
    assert report["edit_plan_artifact_uri"].endswith("edit_plan.json")
    assert report["reel_draft_artifact_uri"].endswith("reel_draft.mp4")


async def test_qc_is_deterministic_for_same_input():
    from agents.qc.handler import run as qc_run

    job_id = uuid.uuid4()
    out1 = await qc_run(_make_state_with_full_upstream(job_id=job_id, target=30))
    out2 = await qc_run(_make_state_with_full_upstream(job_id=job_id, target=30))
    assert (
        out1.artifacts["qc_report"].checksum_sha256
        == out2.artifacts["qc_report"].checksum_sha256
    )


# ---------------------------------------------------------------------------
# Direct handler tests — structural rejections
# ---------------------------------------------------------------------------


async def test_qc_rejects_missing_edit_plan():
    from agents.qc.handler import run as qc_run
    from common.exceptions import StageRejection

    state = _make_state_with_full_upstream(job_id=uuid.uuid4(), omit_edit_plan=True)
    with pytest.raises(StageRejection, match="edit_plan"):
        await qc_run(state)


async def test_qc_rejects_missing_reel_draft():
    from agents.qc.handler import run as qc_run
    from common.exceptions import StageRejection

    state = _make_state_with_full_upstream(job_id=uuid.uuid4(), omit_reel_draft=True)
    with pytest.raises(StageRejection, match="reel_draft"):
        await qc_run(state)


async def test_qc_rejects_missing_script():
    from agents.qc.handler import run as qc_run
    from common.exceptions import StageRejection

    state = _make_state_with_full_upstream(job_id=uuid.uuid4(), omit_script=True)
    with pytest.raises(StageRejection, match="script"):
        await qc_run(state)


# ---------------------------------------------------------------------------
# Direct handler tests — content-level failing checks
# ---------------------------------------------------------------------------


async def test_qc_fails_on_incomplete_segments():
    """edit_plan with only [hook, body] (no cta) → segments_present check fails."""
    from agents.qc.handler import run as qc_run

    bad_segments = [
        {
            "segment_type": "hook",
            "start_seconds": 0.0,
            "end_seconds": 6.0,
            "duration_seconds": 6.0,
            "text": "h",
            "metadata": {},
        },
        {
            "segment_type": "body",
            "start_seconds": 6.0,
            "end_seconds": 30.0,
            "duration_seconds": 24.0,
            "text": "b",
            "metadata": {},
        },
    ]
    state = _make_state_with_full_upstream(
        job_id=uuid.uuid4(), target=30, edit_plan_segments=bad_segments
    )
    output = await qc_run(state)
    report = output.artifacts["qc_report"].extra["qc_report"]
    assert report["passed"] is False
    failing = [c for c in report["checks"] if c["decision"] == "fail"]
    assert any(c["name"] == "segments_present" for c in failing)
    assert report["segment_count"] == 2


async def test_qc_fails_on_total_duration_mismatch():
    """Three hook/body/cta segments that don't sum to target."""
    from agents.qc.handler import run as qc_run

    short_segments = [
        {
            "segment_type": "hook",
            "start_seconds": 0.0,
            "end_seconds": 4.0,
            "duration_seconds": 4.0,
            "text": "h",
            "metadata": {},
        },
        {
            "segment_type": "body",
            "start_seconds": 4.0,
            "end_seconds": 20.0,
            "duration_seconds": 16.0,
            "text": "b",
            "metadata": {},
        },
        {
            "segment_type": "cta",
            "start_seconds": 20.0,
            "end_seconds": 25.0,
            "duration_seconds": 5.0,
            "text": "c",
            "metadata": {},
        },
    ]  # sums to 25s, target 30s
    state = _make_state_with_full_upstream(
        job_id=uuid.uuid4(), target=30, edit_plan_segments=short_segments
    )
    output = await qc_run(state)
    report = output.artifacts["qc_report"].extra["qc_report"]
    assert report["passed"] is False
    fail_names = [c["name"] for c in report["checks"] if c["decision"] == "fail"]
    assert "total_duration_matches_target" in fail_names


async def test_qc_warns_when_reel_draft_has_local_path():
    """Phase 3I expects reel_draft to be a stub. A local_path triggers a warn
    (not a fail), and the overall report becomes passed=False."""
    from agents.qc.handler import run as qc_run

    state = _make_state_with_full_upstream(
        job_id=uuid.uuid4(),
        target=30,
        reel_draft_local_path="/tmp/should/not/be/here.mp4",
    )
    output = await qc_run(state)
    report = output.artifacts["qc_report"].extra["qc_report"]
    # Overall pass is "all checks must be pass"; warn fails the overall.
    assert report["passed"] is False
    warn_names = [c["name"] for c in report["checks"] if c["decision"] == "warn"]
    assert "reel_draft_is_stub" in warn_names


async def test_qc_passes_with_phase3h_stub_reel_draft():
    """The standard Phase 3H stub (no local_path, s3:// URI) passes QC."""
    from agents.qc.handler import run as qc_run

    state = _make_state_with_full_upstream(
        job_id=uuid.uuid4(), target=30, reel_draft_local_path=None
    )
    output = await qc_run(state)
    report = output.artifacts["qc_report"].extra["qc_report"]
    stub_check = next(c for c in report["checks"] if c["name"] == "reel_draft_is_stub")
    assert stub_check["decision"] == "pass"


# ---------------------------------------------------------------------------
# End-to-end DAG
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_under_test(monkeypatch, tmp_path):
    monkeypatch.setenv("PROVIDED_AUDIO_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("PROVIDED_IMAGE_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("SCRIPTWRITER_BACKEND", "template")

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
        yield client, fake, tmp_path

    await fake.aclose()
    queue_publisher.reset_redis_client()
    await core_db.async_reset_engine()


def _runner_config():
    from agents.orchestrator.dag import DagRunnerConfig

    return DagRunnerConfig(
        signing_key="phase3i-test-key-not-for-prod",
        allowed_lipsync_backend="sadtalker",
        token_ttl_seconds=3600,
    )


def _valid_payload() -> dict:
    return {
        "brief": "Three calming bedtime habits for better sleep.",
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "target_duration_seconds": 30,
        "watermark_required": True,
        "c2pa_required": True,
        "script_text": (
            "Quick: three tips for sleep.\n\n"
            "First avoid screens. Second cool room. Third stick to a schedule.\n\n"
            "Save this for later."
        ),
    }


async def test_dag_promotes_qc_report_artifact_as_metadata(app_under_test):
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact
    from common.enums import ArtifactType

    client, _, _ = app_under_test
    r = await client.post("/jobs", json=_valid_payload())
    job_id = uuid.UUID(r.json()["id"])
    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "published"

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(
                Artifact.job_id == job_id,
                Artifact.artifact_type == ArtifactType.metadata.value,
            )
        )
        rows = list(result.scalars().all())
    # Exactly one metadata artifact for this job — the QC report.
    assert len(rows) == 1
    row = rows[0]
    assert row.mime_type == "application/json"
    assert row.checksum_sha256 and len(row.checksum_sha256) == 64
    report = (row.metadata_json or {}).get("qc_report")
    assert report is not None
    assert report["passed"] is True
    assert [c["name"] for c in report["checks"]] == [
        "script_artifact_present",
        "segments_present",
        "total_duration_matches_target",
        "reel_draft_is_stub",
    ]
    assert all(c["decision"] == "pass" for c in report["checks"])
    # Back-references resolve.
    assert report["script_artifact_uri"].endswith("script.json")
    assert report["edit_plan_artifact_uri"].endswith("edit_plan.json")
    assert report["reel_draft_artifact_uri"].endswith("reel_draft.mp4")
    assert (row.metadata_json or {}).get("qc_passed") is True


# ---------------------------------------------------------------------------
# Import discipline
# ---------------------------------------------------------------------------


def test_qc_module_has_no_media_or_ml_imports():
    code = (
        "import json, sys\n"
        "from agents.qc.handler import run\n"
        "forbidden = ['ffmpeg', 'ffprobe', 'mediainfo', 'moviepy',\n"
        "             'cv2', 'opencv', 'imageio', 'numpy', 'PIL',\n"
        "             'torch', 'diffusers', 'transformers',\n"
        "             'soundfile', 'librosa']\n"
        "loaded = sorted(m for m in forbidden if m in sys.modules)\n"
        "print(json.dumps(loaded))\n"
    )
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert loaded == [], f"qc handler pulled in media/ML libs: {loaded}"
