"""DAG runner — Phase 2.

A hand-rolled state machine over the stage list defined in
`pipelines/reel_default.yaml`. Each stage is a no-op handler in Phase 2;
real implementations land in Phase 3+ behind the same handler interfaces.

Why not LangGraph yet?
    LangGraph is the right tool when there are branches, retries, parallel
    fan-outs, or human-in-the-loop checkpoints. Phase 2 has none of these
    — the DAG is linear with a single early-exit on rejection. Pulling in
    `langgraph` + `langchain-core` for that would add a dependency tree
    larger than this whole file. The handler interface here is
    deliberately compatible with a LangGraph node so swapping later is a
    50-line refactor, not a rewrite.

Persistence:
    Per-stage progress lives in the `stage_runs` table (see
    `app/models/stage_run.py`). The DagState dataclass is purely
    in-memory. We do **not** use a LangGraph Postgres checkpointer in
    Phase 2 — that would require additional langgraph-checkpoint-postgres
    machinery and the simple stage_runs table is sufficient for now.

Coupling note:
    This module imports `app.*` for DB access. That coupling is
    intentional and documented as a Phase 2 limitation in
    `agents/orchestrator/README.md`. Phase 3+ may extract a small
    `common.db` package.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.enums import ComplianceDecisionType, JobStatus, StageName, StageStatus
from common.exceptions import StageError, StageRejection
from common.schemas import DagState, StageOutput

# Backend imports — Phase 2 coupling; tracked for Phase 3 refactor.
from app.models.compliance import ComplianceEvent
from app.models.job import Job
from app.services import job_service, stage_run_service

from agents.compliance_officer import (
    export_disclosure_validation,
    identity_guard,
    pre_lipsync_auth,
)
from agents.compliance_officer.policy_gate import JobBriefView, policy_gate
from agents.editor.handler import run as editor_run
from agents.face.handler import run as face_run
from agents.lipsync.handler import run as lipsync_run
from agents.publisher.handler import run as publisher_run
from agents.qc.handler import run as qc_run
from agents.scriptwriter.handler import run as scriptwriter_run
from agents.voice.handler import run as voice_run

log = logging.getLogger(__name__)


_DEFAULT_PIPELINE_PATH = Path(__file__).resolve().parents[2] / "pipelines" / "reel_default.yaml"

# Stages handled directly by this runner rather than via the generic
# handler interface (because they take extra constructor params).
_COMPLIANCE_GATES = {
    StageName.policy_gate.value,
    StageName.identity_guard.value,
    StageName.pre_lipsync_auth.value,
    StageName.export_disclosure_validation.value,
}


def load_stage_order(pipeline_path: Path | None = None) -> list[str]:
    """Read the canonical stage order from a pipeline YAML.

    The YAML uses `${VAR:-default}` shell-style interpolation in `params`
    blocks; `yaml.safe_load` treats those as strings so we never have to
    evaluate them here. We only care about the ordered `stages[].id` list.
    """
    path = pipeline_path or _DEFAULT_PIPELINE_PATH
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [s["id"] for s in (data.get("stages") or []) if "id" in s]


@dataclass
class DagRunnerConfig:
    signing_key: str
    allowed_lipsync_backend: str
    token_ttl_seconds: int = 3600
    pipeline_path: Path | None = None


HandlerNoArgs = Callable[[DagState], Awaitable[StageOutput]]


class DagRunner:
    """Run the no-op DAG for one job, top to bottom.

    Public surface: `run(job_id) -> JobStatus`.
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        config: DagRunnerConfig,
    ) -> None:
        self._sm = sessionmaker
        self._cfg = config
        self._stage_order = load_stage_order(config.pipeline_path)
        # Map of stage id → handler (only the non-compliance ones; the
        # compliance gates are called with their own extra args inline).
        self._stage_handlers: dict[str, HandlerNoArgs] = {
            StageName.scriptwriter.value: scriptwriter_run,
            StageName.voice.value: voice_run,
            StageName.face.value: face_run,
            StageName.editor.value: editor_run,
            StageName.qc.value: qc_run,
            StageName.publisher.value: publisher_run,
        }

    # ---------------------------------------------------------------- helpers

    async def _load_state(self, job_id: uuid.UUID) -> tuple[DagState, Job]:
        async with self._sm() as session:
            job = await job_service.get_job(session, job_id)
            if job is None:
                raise StageError("orchestrator", f"job {job_id} not found")
            state = DagState(
                job_id=job.id,
                brief=job.brief,
                target_duration_seconds=job.target_duration_seconds,
                synthetic_person_confirmed=job.synthetic_person_confirmed,
                consent_confirmed=job.consent_confirmed,
                watermark_required=job.watermark_required,
                c2pa_required=job.c2pa_required,
            )
            return state, job

    async def _start_stage_row(self, job_id: uuid.UUID, stage: str) -> uuid.UUID:
        async with self._sm() as session:
            run = await stage_run_service.create_pending(
                session, job_id=job_id, stage=stage
            )
            return run.id

    async def _record_stage_success(
        self, run_id: uuid.UUID, output: StageOutput
    ) -> None:
        artifacts_json = {k: v.model_dump(mode="json") for k, v in output.artifacts.items()}
        async with self._sm() as session:
            await stage_run_service.mark_succeeded(
                session,
                run_id,
                artifacts=artifacts_json,
                extra={
                    "notes": output.notes,
                    "noop": output.noop,
                    "extra": _json_safe(output.extra),
                },
            )

    async def _record_stage_rejected(self, run_id: uuid.UUID, reason: str) -> None:
        async with self._sm() as session:
            await stage_run_service.mark_rejected(session, run_id, reason=reason)

    async def _record_stage_failed(self, run_id: uuid.UUID, error: str) -> None:
        async with self._sm() as session:
            await stage_run_service.mark_failed(session, run_id, error=error)

    async def _record_compliance_event(
        self,
        job_id: uuid.UUID,
        gate: str,
        decision: ComplianceDecisionType,
        reasons: list[str],
    ) -> None:
        async with self._sm() as session:
            event = ComplianceEvent(
                job_id=job_id, gate=gate, decision=decision, reasons=reasons
            )
            session.add(event)
            await session.commit()

    async def _set_job_status(
        self,
        job_id: uuid.UUID,
        status: JobStatus,
        rejection_reason: str | None = None,
    ) -> None:
        async with self._sm() as session:
            await job_service.set_job_status(
                session, job_id, status, rejection_reason=rejection_reason
            )

    # ---------------------------------------------------------------- stages

    async def _run_policy_gate(self, state: DagState) -> StageOutput:
        view = JobBriefView(
            job_id=str(state.job_id),
            brief=state.brief,
            synthetic_person_confirmed=state.synthetic_person_confirmed,
            consent_confirmed=state.consent_confirmed,
            watermark_required=state.watermark_required,
            c2pa_required=state.c2pa_required,
        )
        decision = policy_gate(view)
        await self._record_compliance_event(
            state.job_id,
            gate=StageName.policy_gate.value,
            decision=(
                ComplianceDecisionType.accept
                if decision.accepted
                else ComplianceDecisionType.reject
            ),
            reasons=decision.reasons,
        )
        if not decision.accepted:
            raise StageRejection(
                StageName.policy_gate.value, "; ".join(decision.reasons) or "policy rejected"
            )
        # On accept, also flip the Job row to `accepted` to match Phase 1 contract.
        await self._set_job_status(state.job_id, JobStatus.accepted)
        return StageOutput(
            noop=True,
            notes="policy_gate accept",
            extra={"reasons": decision.reasons},
        )

    async def _run_identity_guard(self, state: DagState) -> StageOutput:
        try:
            output = await identity_guard.run(state)
        except StageRejection as exc:
            await self._record_compliance_event(
                state.job_id,
                gate=StageName.identity_guard.value,
                decision=ComplianceDecisionType.reject,
                reasons=[exc.reason],
            )
            raise
        await self._record_compliance_event(
            state.job_id,
            gate=StageName.identity_guard.value,
            decision=ComplianceDecisionType.accept,
            reasons=[],
        )
        return output

    async def _run_pre_lipsync_auth(self, state: DagState) -> StageOutput:
        try:
            output = await pre_lipsync_auth.run(
                state,
                signing_key=self._cfg.signing_key,
                allowed_lipsync_backend=self._cfg.allowed_lipsync_backend,
                token_ttl_seconds=self._cfg.token_ttl_seconds,
            )
        except StageRejection as exc:
            await self._record_compliance_event(
                state.job_id,
                gate=StageName.pre_lipsync_auth.value,
                decision=ComplianceDecisionType.reject,
                reasons=[exc.reason],
            )
            raise
        await self._record_compliance_event(
            state.job_id,
            gate=StageName.pre_lipsync_auth.value,
            decision=ComplianceDecisionType.accept,
            reasons=[],
        )
        # Promote the minted token into shared state so LipSync can read it.
        token = output.extra.get("compliance_token")
        if not isinstance(token, str):
            raise StageError(
                StageName.pre_lipsync_auth.value,
                "pre_lipsync_auth did not return a compliance_token string",
            )
        state.compliance_token = token
        return output

    async def _run_lipsync(self, state: DagState) -> StageOutput:
        return await lipsync_run(
            state,
            signing_key=self._cfg.signing_key,
            expected_backend=self._cfg.allowed_lipsync_backend,
        )

    async def _run_export_disclosure_validation(self, state: DagState) -> StageOutput:
        try:
            output = await export_disclosure_validation.run(state)
        except StageRejection as exc:
            await self._record_compliance_event(
                state.job_id,
                gate=StageName.export_disclosure_validation.value,
                decision=ComplianceDecisionType.reject,
                reasons=[exc.reason],
            )
            raise
        await self._record_compliance_event(
            state.job_id,
            gate=StageName.export_disclosure_validation.value,
            decision=ComplianceDecisionType.accept,
            reasons=[],
        )
        return output

    async def _dispatch(self, stage: str, state: DagState) -> StageOutput:
        if stage == StageName.policy_gate.value:
            return await self._run_policy_gate(state)
        if stage == StageName.identity_guard.value:
            return await self._run_identity_guard(state)
        if stage == StageName.pre_lipsync_auth.value:
            return await self._run_pre_lipsync_auth(state)
        if stage == StageName.lipsync.value:
            return await self._run_lipsync(state)
        if stage == StageName.export_disclosure_validation.value:
            return await self._run_export_disclosure_validation(state)
        handler = self._stage_handlers.get(stage)
        if handler is None:
            raise StageError("orchestrator", f"no handler registered for stage {stage!r}")
        return await handler(state)

    # ---------------------------------------------------------------- driver

    async def run(self, job_id: uuid.UUID) -> JobStatus:
        """Execute the full DAG for one job. Returns the final JobStatus."""
        state, _job = await self._load_state(job_id)

        for stage in self._stage_order:
            run_id = await self._start_stage_row(state.job_id, stage)
            try:
                output = await self._dispatch(stage, state)
            except StageRejection as exc:
                await self._record_stage_rejected(run_id, exc.reason)
                state.rejected = True
                state.rejection_reason = exc.reason
                state.rejected_at_stage = StageName(stage) if stage in {s.value for s in StageName} else None
                await self._set_job_status(
                    state.job_id, JobStatus.rejected, rejection_reason=exc.reason
                )
                log.info("dag: job %s rejected at %s: %s", job_id, stage, exc.reason)
                return JobStatus.rejected
            except StageError as exc:
                await self._record_stage_failed(run_id, exc.reason)
                await self._set_job_status(
                    state.job_id, JobStatus.failed, rejection_reason=exc.reason
                )
                log.warning("dag: job %s failed at %s: %s", job_id, stage, exc.reason)
                return JobStatus.failed
            except Exception as exc:  # noqa: BLE001 — catch-all for the DAG driver
                msg = f"{type(exc).__name__}: {exc}"
                await self._record_stage_failed(run_id, msg)
                await self._set_job_status(
                    state.job_id, JobStatus.failed, rejection_reason=msg
                )
                log.exception("dag: job %s unexpected error at %s", job_id, stage)
                return JobStatus.failed

            await self._record_stage_success(run_id, output)
            state.stage_outputs[stage] = output
            state.completed_stages.append(stage)

        await self._set_job_status(state.job_id, JobStatus.published)
        return JobStatus.published


def _json_safe(value):
    """Ensure a dict can survive json.dumps — datetimes etc. become strings."""
    return json.loads(json.dumps(value, default=str))
