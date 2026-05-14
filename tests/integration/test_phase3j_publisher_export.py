"""Phase 3J integration tests — publisher contract + final_export artifact.

What we verify:

Publisher handler — direct calls:
- Happy path: emits a ``final_export`` artifact when QC passed; uses
  ``ArtifactType.final_export``; mime ``application/json``; structured
  ``FinalExport`` carries back-references to qc_report + reel_draft +
  the watermark / C2PA flags + status='published' + disclosure_status='pending'.
- Refuses with ``StageRejection`` when:
  - ``qc_report`` artifact is missing;
  - ``reel_draft`` artifact is missing;
  - ``qc_passed`` is False on the QC report;
  - the export_disclosure_validation gate didn't run (existing rule);
  - ``watermark_required`` or ``c2pa_required`` is False (existing rule).
- Writes NO files to disk (verified by tmp_path scan).

End-to-end through the DAG:
- A valid job produces an ``artifacts`` row with
  ``artifact_type == ArtifactType.final_export.value`` whose
  ``metadata_json["final_export"]`` matches the structured manifest.

Import discipline:
- Importing ``agents.publisher.handler`` does NOT pull in any HTTP /
  cloud-storage client (``requests``, ``httpx``, ``aiohttp``, ``boto3``,
  ``botocore``, ``aiobotocore``, ``minio``) or any media / ML library
  (``ffmpeg``, ``moviepy``, ``cv2``, ``imageio``, ``numpy``, ``PIL``,
  ``torch``, ``diffusers``, ``transformers``).

Boundaries:
- No real video encoding. No C2PA signing. No external uploads.
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
# Helpers — manual DagState assembly mimicking upstream stages
# ---------------------------------------------------------------------------


def _make_state_with_full_upstream(
    *,
    job_id: uuid.UUID,
    target: int = 30,
    omit_qc: bool = False,
    omit_reel_draft: bool = False,
    omit_disclosure: bool = False,
    qc_passed: bool = True,
    watermark_required: bool = True,
    c2pa_required: bool = True,
):
    """Build a DagState that mimics scriptwriter + lipsync + editor +
    export_disclosure_validation + qc having run."""
    from common.schemas import ArtifactRef, DagState, StageOutput

    state = DagState(
        job_id=job_id,
        brief="Sleep tips",
        target_duration_seconds=target,
        synthetic_person_confirmed=True,
        consent_confirmed=True,
        watermark_required=watermark_required,
        c2pa_required=c2pa_required,
    )

    state.stage_outputs["scriptwriter"] = StageOutput(
        artifacts={
            "script": ArtifactRef(
                artifact_type="script",
                uri=f"s3://bucket/{job_id}/script.json",
                mime_type="application/json",
                checksum_sha256="aa" * 32,
                size_bytes=42,
                extra={"structured_script": {"hook": "h", "body": "b", "cta": "c"}},
            )
        }
    )

    state.stage_outputs["lipsync"] = StageOutput(
        artifacts={
            "talking_head": ArtifactRef(
                artifact_type="video",
                uri=f"s3://bucket/{job_id}/talking_head.mp4",
            )
        }
    )

    editor_artifacts: dict = {
        "edit_plan": ArtifactRef(
            artifact_type="edit_plan",
            uri=f"s3://bucket/{job_id}/edit_plan.json",
            mime_type="application/json",
            checksum_sha256="bb" * 32,
            size_bytes=64,
        ),
    }
    if not omit_reel_draft:
        editor_artifacts["reel_draft"] = ArtifactRef(
            artifact_type="video",
            uri=f"s3://bucket/{job_id}/reel_draft.mp4",
            extra={"phase": "phase3h_stub"},
        )
    state.stage_outputs["editor"] = StageOutput(artifacts=editor_artifacts)

    if not omit_disclosure:
        state.stage_outputs["export_disclosure_validation"] = StageOutput(
            artifacts={},
        )

    if not omit_qc:
        state.stage_outputs["qc"] = StageOutput(
            artifacts={
                "qc_report": ArtifactRef(
                    artifact_type="metadata",
                    uri=f"s3://bucket/{job_id}/qc_report.json",
                    mime_type="application/json",
                    checksum_sha256="cc" * 32,
                    size_bytes=128,
                    extra={
                        "qc_passed": qc_passed,
                        "qc_report": {
                            "passed": qc_passed,
                            "checks": [
                                {"name": "x", "decision": "pass", "detail": ""}
                            ],
                        },
                    },
                )
            }
        )

    return state


# ---------------------------------------------------------------------------
# Direct handler tests — happy path
# ---------------------------------------------------------------------------


async def test_publisher_emits_final_export_when_qc_passed():
    from agents.publisher.handler import run as publisher_run
    from common.enums import ArtifactType

    job_id = uuid.uuid4()
    state = _make_state_with_full_upstream(job_id=job_id, target=30, qc_passed=True)
    output = await publisher_run(state)

    assert "final_export" in output.artifacts
    ref = output.artifacts["final_export"]
    assert ref.artifact_type == ArtifactType.final_export.value
    assert ref.mime_type == "application/json"
    assert ref.checksum_sha256 and len(ref.checksum_sha256) == 64
    assert ref.size_bytes and ref.size_bytes > 0

    manifest = ref.extra["final_export"]
    assert manifest["passed_qc"] is True
    assert manifest["status"] == "published"
    assert manifest["job_id"] == str(job_id)
    assert manifest["source_reel_draft_uri"].endswith("reel_draft.mp4")
    assert manifest["qc_report_uri"].endswith("qc_report.json")
    assert manifest["export_uri"].endswith("reel_final.mp4")
    assert manifest["export_type"] == "video/mp4"
    assert manifest["mime_type"] == "video/mp4"
    assert manifest["watermark_required"] is True
    assert manifest["c2pa_required"] is True
    assert manifest["disclosure_status"] == "pending"
    assert manifest["target_duration_seconds"] == pytest.approx(30.0)


async def test_publisher_keeps_legacy_reel_final_and_sidecar_stubs():
    """A future real-export phase can drop into the same artifact names."""
    from agents.publisher.handler import run as publisher_run

    state = _make_state_with_full_upstream(job_id=uuid.uuid4(), target=30)
    output = await publisher_run(state)

    assert "reel_final" in output.artifacts
    assert "sidecar" in output.artifacts
    assert output.artifacts["reel_final"].uri.endswith("reel_final.mp4")
    assert output.artifacts["sidecar"].uri.endswith("sidecar.json")
    # The stubs cross-reference the final_export manifest URI.
    assert output.artifacts["reel_final"].extra["final_export_uri"].endswith(
        "final_export.json"
    )
    assert output.artifacts["sidecar"].extra["final_export_uri"].endswith(
        "final_export.json"
    )


async def test_publisher_is_deterministic_for_same_input():
    from agents.publisher.handler import run as publisher_run

    job_id = uuid.uuid4()
    out1 = await publisher_run(_make_state_with_full_upstream(job_id=job_id, target=30))
    out2 = await publisher_run(_make_state_with_full_upstream(job_id=job_id, target=30))
    assert (
        out1.artifacts["final_export"].checksum_sha256
        == out2.artifacts["final_export"].checksum_sha256
    )


# ---------------------------------------------------------------------------
# Direct handler tests — rejection paths
# ---------------------------------------------------------------------------


async def test_publisher_refuses_when_qc_report_missing():
    from agents.publisher.handler import run as publisher_run
    from common.exceptions import StageRejection

    state = _make_state_with_full_upstream(job_id=uuid.uuid4(), omit_qc=True)
    with pytest.raises(StageRejection, match="qc_report"):
        await publisher_run(state)


async def test_publisher_refuses_when_reel_draft_missing():
    from agents.publisher.handler import run as publisher_run
    from common.exceptions import StageRejection

    state = _make_state_with_full_upstream(job_id=uuid.uuid4(), omit_reel_draft=True)
    with pytest.raises(StageRejection, match="reel_draft"):
        await publisher_run(state)


async def test_publisher_refuses_when_qc_passed_false():
    from agents.publisher.handler import run as publisher_run
    from common.exceptions import StageRejection

    state = _make_state_with_full_upstream(job_id=uuid.uuid4(), qc_passed=False)
    with pytest.raises(StageRejection, match="qc_report"):
        await publisher_run(state)


async def test_publisher_refuses_without_disclosure_validation():
    from agents.publisher.handler import run as publisher_run
    from common.exceptions import StageRejection

    state = _make_state_with_full_upstream(
        job_id=uuid.uuid4(), omit_disclosure=True
    )
    with pytest.raises(StageRejection, match="export_disclosure_validation"):
        await publisher_run(state)


async def test_publisher_refuses_without_watermark_required():
    from agents.publisher.handler import run as publisher_run
    from common.exceptions import StageRejection

    state = _make_state_with_full_upstream(
        job_id=uuid.uuid4(), watermark_required=False
    )
    with pytest.raises(StageRejection, match="watermark"):
        await publisher_run(state)


async def test_publisher_writes_no_files_to_disk(tmp_path, monkeypatch):
    """The publisher must NOT touch the filesystem."""
    from agents.publisher.handler import run as publisher_run

    monkeypatch.chdir(tmp_path)
    state = _make_state_with_full_upstream(job_id=uuid.uuid4(), target=30)
    await publisher_run(state)
    leftovers = list(tmp_path.iterdir())
    assert leftovers == [], f"publisher wrote files: {leftovers}"


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
        signing_key="phase3j-test-key-not-for-prod",
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


async def test_dag_promotes_final_export_artifact(app_under_test):
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
                Artifact.artifact_type == ArtifactType.final_export.value,
            )
        )
        rows = list(result.scalars().all())
    assert len(rows) == 1
    row = rows[0]
    assert row.mime_type == "application/json"
    assert row.checksum_sha256 and len(row.checksum_sha256) == 64
    manifest = (row.metadata_json or {}).get("final_export")
    assert manifest is not None
    assert manifest["passed_qc"] is True
    assert manifest["status"] == "published"
    assert manifest["job_id"] == str(job_id)
    # Back-references resolve.
    assert manifest["source_reel_draft_uri"].endswith("reel_draft.mp4")
    assert manifest["qc_report_uri"].endswith("qc_report.json")
    assert manifest["export_uri"].endswith("reel_final.mp4")


# ---------------------------------------------------------------------------
# Import discipline
# ---------------------------------------------------------------------------


def test_publisher_module_has_no_http_or_media_imports():
    """Phase 3J refuses real uploads + real encoding. No HTTP client, no
    cloud-storage client, no media library may be pulled in at import."""
    code = (
        "import json, sys\n"
        "from agents.publisher.handler import run\n"
        "forbidden = ['requests', 'httpx', 'aiohttp', 'urllib3',\n"
        "             'boto3', 'botocore', 'aiobotocore', 'minio',\n"
        "             'google.cloud', 'ffmpeg', 'moviepy', 'cv2',\n"
        "             'opencv', 'imageio', 'numpy', 'PIL',\n"
        "             'torch', 'diffusers', 'transformers',\n"
        "             'c2pa']\n"
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
    assert loaded == [], f"publisher pulled in forbidden libs: {loaded}"
