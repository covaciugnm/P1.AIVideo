"""Editor — Phase 2 no-op handler.

Real compositing (ffmpeg + MoviePy, subs, music, B-roll, the burned-in
"AI-generated" overlay) lands in Phase 3+. Phase 2 only emits a stub
reel_draft.mp4 reference.

Even at no-op level, the handler refuses if `watermark_required` is false —
this matches the production rule (Editor refuses to render without the
disclosure overlay path enabled).
"""
from __future__ import annotations

from common.enums import StageName
from common.exceptions import StageRejection
from common.schemas import ArtifactRef, DagState, StageOutput


def _stub_uri(job_id: str, filename: str) -> str:
    return f"s3://aivideo-jobs/{job_id}/{filename}"


async def run(state: DagState) -> StageOutput:
    if not state.watermark_required:
        raise StageRejection(StageName.editor.value, "watermark_required must be true")

    talking_head_output = state.stage_outputs.get(StageName.lipsync.value)
    if talking_head_output is None or "talking_head" not in talking_head_output.artifacts:
        raise StageRejection(StageName.editor.value, "upstream lipsync missing talking_head")

    reel_draft_ref = ArtifactRef(
        kind="video",
        uri=_stub_uri(str(state.job_id), "reel_draft.mp4"),
        extra={
            "width": 1080,
            "height": 1920,
            "watermark_burned_in": False,  # noop — would be True after Phase 3
            "phase": "phase2_noop",
        },
    )
    return StageOutput(
        noop=True,
        notes="editor no-op: real ffmpeg compositing lands in Phase 3+",
        artifacts={"reel_draft": reel_draft_ref},
    )
