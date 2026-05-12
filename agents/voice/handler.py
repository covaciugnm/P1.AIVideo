"""Voice — Phase 2 no-op handler.

Real TTS (Piper / XTTS-v2 synthetic voices) lands in Phase 3. Phase 2
only emits stub references for narration + phonemes so downstream stages
can verify that the metadata flows correctly.

No audio is generated. No voice cloning code is or will ever be reachable
from this handler — see docs/compliance/policy.md.
"""
from __future__ import annotations

from common.enums import StageName
from common.exceptions import StageRejection
from common.schemas import ArtifactRef, DagState, StageOutput


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


async def run(state: DagState) -> StageOutput:
    script_output = state.stage_outputs.get(StageName.scriptwriter.value)
    if script_output is None or "script" not in script_output.artifacts:
        raise StageRejection(StageName.voice.value, "scriptwriter did not produce a script artifact")

    narration_ref = ArtifactRef(
        kind="audio",
        uri=_stub_uri(str(state.job_id), "narration.wav"),
        extra={"sample_rate": 48000, "channels": 1, "phase": "phase2_noop"},
    )
    phonemes_ref = ArtifactRef(
        kind="json",
        uri=_stub_uri(str(state.job_id), "phonemes.json"),
        extra={"phase": "phase2_noop"},
    )
    return StageOutput(
        noop=True,
        notes="voice no-op: real TTS lands in Phase 3 (synthetic voices only)",
        artifacts={"narration": narration_ref, "phonemes": phonemes_ref},
    )
