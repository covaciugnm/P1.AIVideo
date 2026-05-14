"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef } from "react";

import { ArtifactTable } from "@/components/ArtifactTable";
import { ComplianceEvents } from "@/components/ComplianceEvents";
import { ErrorMessage } from "@/components/ErrorMessage";
import { FinalExportCard } from "@/components/FinalExportCard";
import { LoadingState } from "@/components/LoadingState";
import { ProgressBar } from "@/components/ProgressBar";
import { QcReportCard } from "@/components/QcReportCard";
import { useSettings } from "@/components/SettingsContext";
import { StageTimeline } from "@/components/StageTimeline";
import { StatusBadge } from "@/components/StatusBadge";
import {
  ApiError,
  getJob,
  getJobArtifacts,
  getJobComplianceEvents,
  getJobFinalExportOptional,
  getJobProgress,
  getJobQcReportOptional,
  getJobSummary,
  getJobTimeline,
} from "@/lib/api";
import { formatDate, humanize, isTerminalStatus, shortId } from "@/lib/format";
import * as logBus from "@/lib/log-bus";
import type {
  ArtifactResponse,
  ComplianceEventResponse,
  FinalExportResponse,
  JobDetail,
  JobProgress,
  QCReportResponse,
  StageTimelineEntry,
} from "@/lib/types";
import { usePolling } from "@/lib/usePolling";

import styles from "./page.module.css";

interface JobDetailBundle {
  readonly job: JobDetail;
  readonly progress: JobProgress;
  readonly timeline: readonly StageTimelineEntry[];
  readonly artifacts: readonly ArtifactResponse[];
  readonly complianceEvents: readonly ComplianceEventResponse[];
  readonly qcReport: QCReportResponse | null;
  readonly finalExport: FinalExportResponse | null;
}

export default function JobDetailPage({
  params,
}: {
  readonly params: { readonly jobId: string };
}) {
  const { jobId } = params;
  const { settings, hydrated } = useSettings();
  const announcedRef = useRef(false);
  const lastStatusRef = useRef<string | null>(null);
  const lastPathRef = useRef<"summary" | "fallback" | null>(null);

  useEffect(() => {
    if (!announcedRef.current) {
      announcedRef.current = true;
      logBus.emit({
        source: "frontend",
        level: "info",
        message: `job detail opened: ${shortId(jobId)}`,
        meta: { jobId },
      });
    }
  }, [jobId]);

  const loader = useCallback(
    async (signal: AbortSignal): Promise<JobDetailBundle> => {
      // Phase 4F-3 primary path: a single /summary round-trip.
      try {
        const summary = await getJobSummary(jobId, signal);
        if (lastPathRef.current !== "summary") {
          logBus.emit({
            source: "frontend",
            level: "info",
            message: `detail loader using /summary (${shortId(jobId)})`,
            meta: { jobId, path: "summary" },
          });
          lastPathRef.current = "summary";
        }
        return {
          job: summary.job,
          progress: summary.progress,
          timeline: summary.timeline,
          artifacts: summary.artifacts,
          complianceEvents: summary.compliance_events,
          qcReport: summary.qc_report,
          finalExport: summary.final_export,
        };
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          throw err;
        }
        // 404 means the job genuinely doesn't exist; surface it directly.
        if (err instanceof ApiError && err.status === 404) {
          throw err;
        }
        // Network or 5xx from /summary — fall back to the seven-fetch
        // path so the UI stays resilient (e.g. older backend without the
        // Phase 4F-2 endpoint, or transient flake on one shard).
        if (lastPathRef.current !== "fallback") {
          const msg = err instanceof Error ? err.message : String(err);
          logBus.emit({
            source: "frontend",
            level: "warning",
            message: `detail loader falling back to multi-fetch (${shortId(jobId)}): ${msg}`,
            meta: { jobId, path: "fallback", reason: msg },
          });
          lastPathRef.current = "fallback";
        }
        const [
          job,
          progress,
          timeline,
          artifacts,
          complianceEvents,
          qcReport,
          finalExport,
        ] = await Promise.all([
          getJob(jobId, signal),
          getJobProgress(jobId, signal),
          getJobTimeline(jobId, signal),
          getJobArtifacts(jobId, signal),
          getJobComplianceEvents(jobId, signal),
          getJobQcReportOptional(jobId, signal),
          getJobFinalExportOptional(jobId, signal),
        ]);
        return {
          job,
          progress,
          timeline,
          artifacts,
          complianceEvents,
          qcReport,
          finalExport,
        };
      }
    },
    [jobId],
  );

  // Polling stays enabled while the job is non-terminal AND auto polling is
  // on. The terminal check uses the latest fetched job.status (see effect
  // below) — usePolling will tear down the timer when ``enabled`` flips.
  const stopPolling = useRef(false);

  const { data, error, loading } = usePolling<JobDetailBundle>(loader, {
    intervalMs: Math.max(1, settings.pollingIntervalSeconds) * 1000,
    enabled: hydrated && settings.autoPollingEnabled && !stopPolling.current,
  });

  useEffect(() => {
    if (!data) return;
    const status = data.job.status;
    if (status !== lastStatusRef.current) {
      const prev = lastStatusRef.current;
      lastStatusRef.current = status;
      logBus.emit({
        source: "frontend",
        level: isTerminalStatus(status) ? "success" : "info",
        message: `job ${shortId(jobId)} status: ${prev ?? "(initial)"} → ${status}`,
        meta: { jobId, status },
      });
      if (isTerminalStatus(status)) {
        stopPolling.current = true;
      }
    }
  }, [data, jobId]);

  return (
    <div>
      <header className={styles.header}>
        <Link href="/" className="muted">
          ← Back to jobs
        </Link>
        <h1 className={styles.title}>
          Job <code>{shortId(jobId)}</code>
        </h1>
      </header>

      {error && <ErrorMessage message={error.message} title="Failed to load job" />}
      {loading && data === null && !error && <LoadingState label="Loading job…" />}
      {data && <JobDetail bundle={data} />}
    </div>
  );
}

function JobDetail({ bundle }: { readonly bundle: JobDetailBundle }) {
  const {
    job,
    progress,
    timeline,
    artifacts,
    complianceEvents,
    qcReport,
    finalExport,
  } = bundle;

  const terminal = isTerminalStatus(job.status);

  return (
    <>
      <section className="card">
        <div className={styles.summaryHeader}>
          <h2>Overview</h2>
          <StatusBadge status={job.status} />
        </div>
        <dl className="kv">
          <dt>Brief</dt>
          <dd>{job.brief}</dd>
          <dt>Target duration</dt>
          <dd>{job.target_duration_seconds} s</dd>
          <dt>Voice mode</dt>
          <dd>{job.voice_mode}</dd>
          {job.face_mode && (
            <>
              <dt>Face mode</dt>
              <dd>{job.face_mode}</dd>
            </>
          )}
          <dt>TTS backend</dt>
          <dd>{job.tts_backend}</dd>
          <dt>Watermark required</dt>
          <dd>{String(job.watermark_required)}</dd>
          <dt>C2PA required</dt>
          <dd>{String(job.c2pa_required)}</dd>
          <dt>Created</dt>
          <dd>{formatDate(job.created_at)}</dd>
          <dt>Updated</dt>
          <dd>{formatDate(job.updated_at)}</dd>
          {job.rejection_reason && (
            <>
              <dt>Rejection reason</dt>
              <dd>{job.rejection_reason}</dd>
            </>
          )}
        </dl>
        <div className={styles.progressBlock}>
          <ProgressBar
            percent={progress.progress_percent}
            completedStages={progress.completed_stages}
            totalStages={progress.total_stages}
            failedStages={progress.failed_stages}
          />
          <StageCountsStrip progress={progress} />
        </div>
        {terminal && (
          <p className="muted">Job is in a terminal state. Polling stopped.</p>
        )}
      </section>

      {job.script_text && (
        <section className="card">
          <h2>Script</h2>
          <pre className={styles.script}>{job.script_text}</pre>
        </section>
      )}

      <section className="card">
        <h2>Stage timeline</h2>
        <StageTimeline stages={progress.stages} timeline={timeline} />
      </section>

      <section className="card">
        <h2>Artifacts ({artifacts.length})</h2>
        <ArtifactTable artifacts={artifacts} />
      </section>

      <section className="card">
        <h2>Compliance events ({complianceEvents.length})</h2>
        <ComplianceEvents events={complianceEvents} />
      </section>

      {qcReport && (
        <section className="card">
          <QcReportCard report={qcReport} />
        </section>
      )}

      {finalExport && (
        <section className="card">
          <FinalExportCard response={finalExport} />
        </section>
      )}
    </>
  );
}

function StageCountsStrip({ progress }: { readonly progress: JobProgress }) {
  // Phase 4F-2 added the flat name lists. They're optional in the TS
  // contract (older payloads may not include them), so fall back to the
  // count fields + derive the lists from ``stages`` when needed.
  const completedCount = progress.completed_stages;
  const failedCount = progress.failed_stages;
  const pendingCount =
    progress.pending_stages ??
    Math.max(0, progress.total_stages - completedCount - failedCount);
  const pendingNames =
    progress.pending_stage_names ??
    progress.stages.filter((s) => s.status === "pending").map((s) => s.stage_name);
  const failedNames =
    progress.failed_stage_names ??
    progress.stages
      .filter((s) => s.status === "failed" || s.status === "rejected")
      .map((s) => s.stage_name);
  return (
    <div className={styles.stageCounts}>
      <span className={styles.stageCountCompleted} title="Completed stages">
        ✓ {completedCount} completed
      </span>
      <span
        className={
          failedCount > 0 ? styles.stageCountFailed : styles.stageCountFailedMuted
        }
        title={failedNames.length > 0 ? failedNames.map(humanize).join(", ") : "No failed stages"}
      >
        ✗ {failedCount} failed
      </span>
      <span className={styles.stageCountPending} title={pendingNames.map(humanize).join(", ")}>
        … {pendingCount} pending
      </span>
      {progress.current_stage && (
        <span className={styles.stageCurrent} title="Current stage">
          → {humanize(progress.current_stage)}
        </span>
      )}
    </div>
  );
}
