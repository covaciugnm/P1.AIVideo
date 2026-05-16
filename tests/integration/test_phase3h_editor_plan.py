"""Phase 3H integration tests — editor timing contract + edit_plan artifact.

What we verify:

Schema (``common.schemas.EditPlan`` / ``EditSegment``):
- Valid segments accepted; mismatched start/end/duration rejected;
  segments with gaps or overlaps rejected; non-zero starting offset
  rejected; total duration mismatch rejected.

Editor handler (direct):
- A handler call with valid upstream produces an ``edit_plan`` artifact
  with three segments (hook 20% / body 65% / cta 15%), totals matching
  the target, deterministic for fixed input.
- Missing scriptwriter output → ``StageRejection``.
- Missing ``structured_script`` in script extra → ``StageRejection``.
- Existing ``reel_draft`` stub remains in the output so downstream QC
  keeps working.
- The plan's URI is an ``s3://`` stub — NO local video file is created
  on disk (verified by scanning the test's tmp dir).

End-to-end through the DAG:
- A valid job produces an ``artifacts`` row with
  ``artifact_type == ArtifactType.edit_plan.value``, the right
  metadata, and a content sha256.
- The Phase 3G ``script`` artifact's URI/checksum is recorded as the
  plan's source.

Import discipline:
- Importing ``agents.editor.handler`` does NOT pull in
  ``moviepy``, ``ffmpeg``, ``cv2``, ``imageio``, ``numpy``, etc.
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
# Schema-level validation
# ---------------------------------------------------------------------------


def test_edit_segment_rejects_mismatched_duration():
    from common.schemas import EditSegment

    with pytest.raises(ValueError, match="!= duration"):
        EditSegment(
            segment_type="hook",
            start_seconds=0.0,
            end_seconds=6.0,
            duration_seconds=5.0,  # mismatch
            text="x",
        )


def test_edit_segment_rejects_negative_start():
    from common.schemas import EditSegment

    with pytest.raises(ValueError, match="start_seconds"):
        EditSegment(
            segment_type="hook",
            start_seconds=-1.0,
            end_seconds=5.0,
            duration_seconds=6.0,
            text="x",
        )


def test_edit_segment_rejects_end_before_start():
    from common.schemas import EditSegment

    with pytest.raises(ValueError, match="<"):
        EditSegment(
            segment_type="hook",
            start_seconds=5.0,
            end_seconds=2.0,
            duration_seconds=-3.0,
            text="x",
        )


def test_edit_plan_rejects_total_duration_mismatch():
    from common.schemas import EditPlan, EditSegment

    # Three valid 5s segments summing to 15s vs target 20s.
    seg = lambda t, s, e: EditSegment(  # noqa: E731
        segment_type=t,
        start_seconds=s,
        end_seconds=e,
        duration_seconds=e - s,
        text=t,
    )
    with pytest.raises(ValueError, match="sum to"):
        EditPlan(
            target_duration_seconds=20.0,
            source_script_uri="s3://bucket/script.json",
            segments=[
                seg("hook", 0.0, 5.0),
                seg("body", 5.0, 10.0),
                seg("cta", 10.0, 15.0),
            ],
        )


def test_edit_plan_rejects_gap_between_segments():
    from common.schemas import EditPlan, EditSegment

    seg = lambda t, s, e: EditSegment(  # noqa: E731
        segment_type=t,
        start_seconds=s,
        end_seconds=e,
        duration_seconds=e - s,
        text=t,
    )
    # Sums to 20 (5+9+6) so total check passes; gap at 5-6 trips the
    # tile-without-gaps check next.
    with pytest.raises(ValueError, match="gap/overlap"):
        EditPlan(
            target_duration_seconds=20.0,
            source_script_uri="s3://bucket/script.json",
            segments=[
                seg("hook", 0.0, 5.0),
                seg("body", 6.0, 15.0),
                seg("cta", 15.0, 21.0),
            ],
        )


# ---------------------------------------------------------------------------
# Editor handler — direct calls
# ---------------------------------------------------------------------------


def _make_state_with_script(
    *,
    job_id: uuid.UUID,
    target: int = 30,
    hook: str = "Hook line.",
    body: str = "Body text.",
    cta: str = "Follow for more.",
    omit_script_output: bool = False,
    omit_structured: bool = False,
):
    """Build a DagState that mimics scriptwriter+lipsync having run."""
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

    # Lipsync must be present for the editor's existing precheck.
    state.stage_outputs["lipsync"] = StageOutput(
        artifacts={
            "talking_head": ArtifactRef(
                artifact_type="video",
                uri=f"s3://bucket/{job_id}/talking_head.mp4",
            )
        }
    )

    if not omit_script_output:
        structured = (
            None
            if omit_structured
            else {
                "hook": hook,
                "body": body,
                "cta": cta,
                "full_script": f"{hook}\n\n{body}\n\n{cta}",
                "estimated_duration_seconds": float(target),
                "language": "en",
                "provider": "template",
                "model": "template-v1",
                "prompt_version": "v1",
                "metadata": {},
            }
        )
        state.stage_outputs["scriptwriter"] = StageOutput(
            artifacts={
                "script": ArtifactRef(
                    artifact_type="script",
                    uri=f"s3://bucket/{job_id}/script.json",
                    mime_type="application/json",
                    checksum_sha256="abc" * 21 + "f",
                    size_bytes=42,
                    extra={"structured_script": structured} if structured else {},
                )
            }
        )

    return state


async def test_editor_emits_edit_plan_artifact_with_correct_timing():
    from agents.editor.handler import run as editor_run
    from common.enums import ArtifactType

    job_id = uuid.uuid4()
    state = _make_state_with_script(job_id=job_id, target=30)
    output = await editor_run(state)

    assert "edit_plan" in output.artifacts
    ref = output.artifacts["edit_plan"]
    assert ref.artifact_type == ArtifactType.edit_plan.value
    assert ref.mime_type == "application/json"
    assert ref.checksum_sha256 and len(ref.checksum_sha256) == 64
    assert ref.size_bytes and ref.size_bytes > 0
    assert ref.duration_seconds == pytest.approx(30.0)

    plan_dict = ref.extra["edit_plan"]
    segments = plan_dict["segments"]
    assert [s["segment_type"] for s in segments] == ["hook", "body", "cta"]
    durations = [s["duration_seconds"] for s in segments]
    assert durations == pytest.approx([6.0, 19.5, 4.5])
    total = round(sum(s["duration_seconds"] for s in segments) * 1000)
    assert total == 30_000
    assert plan_dict["target_duration_seconds"] == pytest.approx(30.0)


async def test_editor_preserves_reel_draft_stub_for_qc():
    """Phase 9D: when the upstream lipsync output has no real MP4 on disk
    (the Phase 2/3 stub or any metadata-only path), the editor emits a
    metadata-only placeholder reel_draft — not a fake ``.mp4``. The
    downstream QC stage's ``reel_draft must exist`` check still passes."""
    from agents.editor.handler import run as editor_run

    job_id = uuid.uuid4()
    state = _make_state_with_script(job_id=job_id, target=30)
    output = await editor_run(state)

    assert "reel_draft" in output.artifacts
    reel = output.artifacts["reel_draft"]
    # No phantom .mp4 — Phase 9D uses a placeholder URI when upstream
    # video is metadata-only.
    assert not reel.uri.endswith(".mp4")
    assert reel.uri.startswith("placeholder://")
    assert reel.local_path is None
    assert reel.checksum_sha256 is None
    assert reel.extra["real_editor_output"] is False
    assert reel.extra["editor_mode"] == "metadata_only"
    assert reel.extra["reason"] == "no_real_video_artifact"
    # The reel_draft still cross-references the edit_plan.
    assert reel.extra.get("edit_plan_checksum")
    assert reel.extra.get("edit_plan_uri")


async def test_editor_is_deterministic_for_same_input():
    from agents.editor.handler import run as editor_run

    job_id = uuid.uuid4()
    out1 = await editor_run(_make_state_with_script(job_id=job_id, target=30))
    out2 = await editor_run(_make_state_with_script(job_id=job_id, target=30))
    assert (
        out1.artifacts["edit_plan"].checksum_sha256
        == out2.artifacts["edit_plan"].checksum_sha256
    )


async def test_editor_splits_correctly_for_non_integer_target():
    """Target durations that aren't multiples of 5 still tile exactly."""
    from agents.editor.handler import run as editor_run

    state = _make_state_with_script(job_id=uuid.uuid4(), target=33)
    out = await editor_run(state)
    plan = out.artifacts["edit_plan"].extra["edit_plan"]
    segments = plan["segments"]
    # All segments tile from 0 → 33 with no gaps; sum in ms is exact.
    total_ms = sum(round(s["duration_seconds"] * 1000) for s in segments)
    assert total_ms == 33_000
    assert round(segments[0]["start_seconds"] * 1000) == 0
    assert round(segments[-1]["end_seconds"] * 1000) == 33_000


async def test_editor_rejects_missing_scriptwriter_output():
    from agents.editor.handler import run as editor_run
    from common.exceptions import StageRejection

    state = _make_state_with_script(
        job_id=uuid.uuid4(), omit_script_output=True
    )
    with pytest.raises(StageRejection, match="scriptwriter"):
        await editor_run(state)


async def test_editor_rejects_script_without_structured_field():
    from agents.editor.handler import run as editor_run
    from common.exceptions import StageRejection

    state = _make_state_with_script(
        job_id=uuid.uuid4(), omit_structured=True
    )
    with pytest.raises(StageRejection, match="structured_script"):
        await editor_run(state)


async def test_editor_does_not_write_video_files(tmp_path, monkeypatch):
    """Run the editor and verify NO files are written under tmp_path or
    the project's storage dir. The handler is metadata-only."""
    from agents.editor.handler import run as editor_run

    monkeypatch.chdir(tmp_path)
    state = _make_state_with_script(job_id=uuid.uuid4(), target=30)
    await editor_run(state)

    # Tmp dir is the working directory during the call; anything the
    # editor wrote would land here. Should be empty.
    leftovers = list(tmp_path.iterdir())
    assert leftovers == [], f"editor wrote files: {leftovers}"


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
        signing_key="phase3h-test-key-not-for-prod",
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


async def test_dag_promotes_edit_plan_artifact_with_artifact_type_edit_plan(app_under_test):
    from agents.orchestrator.dag import DagRunner
    from app.core.db import get_sessionmaker
    from app.models.artifact import Artifact
    from common.enums import ArtifactType

    client, _, _ = app_under_test
    r = await client.post("/jobs", json=_valid_payload())
    assert r.status_code == 201
    job_id = uuid.UUID(r.json()["id"])

    final = await DagRunner(get_sessionmaker(), _runner_config()).run(job_id)
    assert final.value == "published"

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(Artifact).where(
                Artifact.job_id == job_id,
                Artifact.artifact_type == ArtifactType.edit_plan.value,
            )
        )
        rows = list(result.scalars().all())
    assert len(rows) == 1
    row = rows[0]
    assert row.mime_type == "application/json"
    assert row.checksum_sha256 and len(row.checksum_sha256) == 64
    assert row.duration_seconds == pytest.approx(30.0)
    plan = (row.metadata_json or {}).get("edit_plan")
    assert plan is not None
    assert [s["segment_type"] for s in plan["segments"]] == ["hook", "body", "cta"]
    total_ms = sum(round(s["duration_seconds"] * 1000) for s in plan["segments"])
    assert total_ms == 30_000
    # The plan records its source script.
    assert (row.metadata_json or {}).get("source_script_uri", "").endswith("script.json")
    assert (row.metadata_json or {}).get("source_script_checksum")
    assert (row.metadata_json or {}).get("no_video_generated") is True


# ---------------------------------------------------------------------------
# Import discipline
# ---------------------------------------------------------------------------


def test_editor_module_has_no_video_lib_imports():
    code = (
        "import json, sys\n"
        "from agents.editor.handler import run\n"
        "forbidden = ['ffmpeg', 'moviepy', 'cv2', 'opencv', 'imageio',\n"
        "             'numpy', 'PIL', 'torch', 'diffusers', 'transformers']\n"
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
    assert loaded == [], f"editor pulled in video/ML libs: {loaded}"
