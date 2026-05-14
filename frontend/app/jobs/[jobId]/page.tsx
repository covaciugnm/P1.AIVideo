"use client";

import Link from "next/link";
import { useCallback } from "react";

import { ArtifactTable } from "@/components/ArtifactTable";
import { ComplianceEvents } from "@/components/ComplianceEvents";
import { ErrorMessage } from "@/components/ErrorMessage";
import { FinalExportCard } from "@/components/FinalExportCard";
import { LoadingState } from "@/components/LoadingState";
import { ProgressBar } from "@/components/ProgressBar";
import { QcReportCard } from "@/components/QcReportCard";
import { StageTimeline } from "@/components/StageTimeline";
import { StatusBadge } from "@/components/StatusBadge";
import {
  getJob,
  getJobArtifacts,
  getJobComplianceEvents,
  getJobFinalExportOptional,
  getJobProgress,
  getJobQcReportOptional,
  getJobTimeline,
} from "@/lib/api";
import { formatDate, isTerminalStatus, shortId } from "@/lib/format";
import type {
  ArtifactResponse,
  ComplianceEventResponse,
  FinalExportResponse,
  JobProgress,
  JobResponse,
  QCReportResponse,
  StageTimelineEntry,
} from "@/lib/types";
import { usePolling } from "@/lib/usePolling";

import styles from "./page.module.css";

interface JobDetailBundle {
  readonly job: JobResponse;
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

  const loader = useCallback(
    async (signal: AbortSignal): Promise<JobDetailBundle> => {
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
    },
    [jobId],
  );

  const terminal = false; // will be re-computed once data arrives
  const { data, error, loading } = usePolling<JobDetailBundle>(loader, {
    intervalMs: 3_000,
    enabled: !terminal,
  });

  // Slow polling once terminal: stop the timer entirely by remounting? We
  // keep the simple model — polling is cheap (read-only JSON) — but show a
  // muted note once the job is in a terminal state.

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
      {loading && data === null && <LoadingState label="Loading job…" />}
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
        </div>
        {terminal && (
          <p className="muted">Job is in a terminal state.</p>
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
