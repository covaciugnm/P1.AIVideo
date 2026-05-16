"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ArtifactTable } from "@/components/ArtifactTable";
import { JobRecoveryControls } from "@/components/JobRecoveryControls";
import { VideoArtifactPreview } from "@/components/VideoArtifactPreview";
import { ComplianceEvents } from "@/components/ComplianceEvents";
import { ErrorMessage } from "@/components/ErrorMessage";
import { FinalExportCard } from "@/components/FinalExportCard";
import { HelpHint } from "@/components/HelpHint";
import { LoadingState } from "@/components/LoadingState";
import { ProgressBar } from "@/components/ProgressBar";
import { QcReportCard } from "@/components/QcReportCard";
import { useSettings } from "@/components/SettingsContext";
import { StageTimeline } from "@/components/StageTimeline";
import { StatusBadge } from "@/components/StatusBadge";
import { useT } from "@/lib/i18n/LanguageContext";
import {
  ApiError,
  audioFitCheck,
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
  AudioFitCheckResponse,
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
  const t = useT();
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

  // Phase 5C — opportunistic audio fit-check whenever the job has at
  // least one audio artifact. We re-run when the artifact count changes
  // (e.g. uploaded audio + later TTS-generated audio), not every poll
  // tick, to avoid log spam.
  const [audioFit, setAudioFit] = useState<AudioFitCheckResponse | null>(null);
  const lastFitArtifactCountRef = useRef<number>(-1);

  useEffect(() => {
    if (!data) return;
    const audioCount = data.artifacts.filter((a) => a.artifact_type === "audio").length;
    if (audioCount === 0) {
      if (audioFit !== null) setAudioFit(null);
      lastFitArtifactCountRef.current = 0;
      return;
    }
    if (audioCount === lastFitArtifactCountRef.current) return;
    lastFitArtifactCountRef.current = audioCount;
    const controller = new AbortController();
    (async () => {
      try {
        const fit = await audioFitCheck({ job_id: jobId }, controller.signal);
        setAudioFit(fit);
        logBus.emit({
          source: "frontend",
          level: fit.fit_status === "ok" ? "info" : "warning",
          message: `audio fit ${fit.fit_status} (Δ${fit.delta_seconds}s)`,
          meta: {
            jobId,
            fit_status: fit.fit_status,
            recommendation: fit.recommendation,
          },
        });
      } catch {
        // opportunistic — silent on transient failure.
      }
    })();
    return () => controller.abort();
  }, [data, jobId, audioFit]);

  return (
    <div>
      <header className={styles.header}>
        <Link href="/" className="muted">
          {t("jobDetail.backToJobs")}
        </Link>
        <h1 className={styles.title}>
          {t("jobs.title").replace(/s$/, "")}{" "}<code>{shortId(jobId)}</code>
          <HelpHint slug="job-detail" />
        </h1>
        <div className={styles.headerActions}>
          {(() => {
            const canEdit =
              (data?.job.can_edit ?? data?.job.status !== "published");
            return canEdit ? (
              <Link
                href={`/jobs/${jobId}/edit`}
                className="btn btn-primary"
                aria-label={t("jobDetail.editJob")}
              >
                {t("jobDetail.editJob")}
              </Link>
            ) : (
              <span
                className="btn btn-ghost"
                title={t("editJob.publishedLockedNote")}
                aria-disabled="true"
              >
                {t("editJob.cannotEditThisJob")}
              </span>
            );
          })()}
        </div>
      </header>

      {error && <ErrorMessage message={error.message} title={t("jobs.failedToLoad")} />}
      {loading && data === null && !error && <LoadingState label={t("common.loading")} />}
      {data && <JobDetail bundle={data} fit={audioFit} />}
    </div>
  );
}

function JobDetail({
  bundle,
  fit,
}: {
  readonly bundle: JobDetailBundle;
  readonly fit: AudioFitCheckResponse | null;
}) {
  const t = useT();
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
  const subtitleEnabled = (job as { subtitle_enabled?: boolean }).subtitle_enabled;
  const subtitleLangs =
    (job as { subtitle_languages?: string[] | null }).subtitle_languages ?? [];
  const subtitleFmt =
    (job as { subtitle_format?: string }).subtitle_format ?? "srt";
  const subtitleBurn =
    (job as { subtitle_burn_in?: boolean }).subtitle_burn_in ?? false;

  return (
    <>
      <section className="card">
        <div className={styles.summaryHeader}>
          <h2>{t("jobDetail.overview")}</h2>
          <StatusBadge status={job.status} />
        </div>
        <dl className="kv">
          <dt>{t("jobDetail.briefField")}</dt>
          <dd>{job.brief}</dd>
          <dt>{t("jobDetail.targetDuration")}</dt>
          <dd>{job.target_duration_seconds} s</dd>
          <dt>{t("jobDetail.voiceMode")}</dt>
          <dd>{job.voice_mode}</dd>
          {job.face_mode && (
            <>
              <dt>{t("jobDetail.faceMode")}</dt>
              <dd>{job.face_mode}</dd>
            </>
          )}
          <dt>{t("jobDetail.ttsBackend")}</dt>
          <dd>{job.tts_backend}</dd>
          <dt>{t("jobDetail.watermarkRequired")}</dt>
          <dd>{job.watermark_required ? t("common.yes") : t("common.no")}</dd>
          <dt>{t("jobDetail.c2paRequired")}</dt>
          <dd>{job.c2pa_required ? t("common.yes") : t("common.no")}</dd>
          {/* Phase 11A — language + subtitle surfaces. */}
          <dt>{t("jobDetail.videoLanguage")}</dt>
          <dd>
            <code>{(job as { video_language?: string }).video_language ?? "ro"}</code>
          </dd>
          <dt>{t("jobDetail.subtitles")}</dt>
          <dd>
            {subtitleEnabled ? (
              <>
                {t("jobDetail.subtitlesOn")} (
                {subtitleLangs.join(", ") || "—"}
                ) · {t("jobDetail.subtitleFormat").toLowerCase()}{" "}
                <code>{subtitleFmt}</code>
                {subtitleBurn
                  ? ` · ${t("jobDetail.burnInRequested")}`
                  : ` · ${t("jobDetail.burnInSidecar")}`}
              </>
            ) : (
              t("jobDetail.subtitlesOff")
            )}
          </dd>
          <dt>{t("jobDetail.createdAt")}</dt>
          <dd>{formatDate(job.created_at)}</dd>
          <dt>{t("jobDetail.updatedAt")}</dt>
          <dd>{formatDate(job.updated_at)}</dd>
          {job.rejection_reason && (
            <>
              <dt>{t("jobDetail.rejectionReason")}</dt>
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
          {fit && <FitBanner fit={fit} />}
        </div>
        {terminal && (
          <p className="muted">Job is in a terminal state. Polling stopped.</p>
        )}
      </section>

      {job.script_text && (
        <section className="card">
          <h2>{t("qc.script")}</h2>
          <pre className={styles.script}>{job.script_text}</pre>
        </section>
      )}

      <section className="card">
        <h2>{t("jobDetail.timeline")}</h2>
        <StageTimeline stages={progress.stages} timeline={timeline} />
      </section>

      <section className="card">
        <h2>{t("jobDetail.artifacts")} ({artifacts.length})</h2>
        <ArtifactTable artifacts={artifacts} />
      </section>

      <VideoArtifactPreview artifacts={artifacts} />

      <JobRecoveryControls
        job={job}
        onMutated={() => {
          // Simple refresh — the next poll would catch the change too,
          // but a full reload makes the new state immediately visible.
          if (typeof window !== "undefined") window.location.reload();
        }}
      />

      <section className="card">
        <h2>{t("jobDetail.complianceEvents")} ({complianceEvents.length})</h2>
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

function FitBanner({ fit }: { readonly fit: AudioFitCheckResponse }) {
  const cls =
    fit.fit_status === "ok"
      ? styles.fitOk
      : fit.fit_status === "missing_audio"
        ? styles.fitMuted
        : styles.fitWarn;
  const deltaLabel =
    fit.delta_seconds === null
      ? "—"
      : `${fit.delta_seconds > 0 ? "+" : ""}${fit.delta_seconds.toFixed(2)}s`;
  return (
    <div className={`${styles.fitBanner} ${cls}`}>
      <span>
        Audio fit: <strong>{humanize(fit.fit_status)}</strong>
      </span>
      <span className={styles.fitMeta}>
        target {fit.target_duration_seconds}s · audio{" "}
        {fit.audio_duration_seconds !== null
          ? `${fit.audio_duration_seconds.toFixed(2)}s`
          : "—"}{" "}
        · Δ {deltaLabel}
      </span>
      {fit.fit_status !== "ok" && (
        <span className={styles.fitRec}>
          → {humanize(fit.recommendation)}
        </span>
      )}
    </div>
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
