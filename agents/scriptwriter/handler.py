"""Scriptwriter — Phase 2 no-op handler.

Phase 1 didn't run this stage at all; Phase 2 runs it as part of the DAG
but emits no real content. The real LLM-driven scriptwriter lands in
Phase 3 alongside the vLLM service and the prompt templates under
configs/prompts/scriptwriter/.

The no-op produces a stub `script.json` artifact reference. No file is
written to MinIO; the URI is a placeholder that future stages can read
as metadata only.
"""
from __future__ import annotations

from common.enums import StageName
from common.exceptions import StageRejection
from common.schemas import ArtifactRef, DagState, StageOutput


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


async def run(state: DagState) -> StageOutput:
    if not state.brief.strip():
        raise StageRejection(StageName.scriptwriter.value, "brief is empty")

    script_ref = ArtifactRef(
        artifact_type="json",
        uri=_stub_uri(str(state.job_id), "script.json"),
        extra={
            "estimated_duration_sec": state.target_duration_seconds,
            "language": "en",
            "phase": "phase2_noop",
        },
    )
    return StageOutput(
        noop=True,
        notes="scriptwriter no-op: real LLM scripting lands in Phase 3",
        artifacts={"script": script_ref},
    )
