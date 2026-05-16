"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ErrorMessage } from "@/components/ErrorMessage";
import { HelpHint } from "@/components/HelpHint";
import { LoadingState } from "@/components/LoadingState";
import { ProgressBar } from "@/components/ProgressBar";
import { useSettings } from "@/components/SettingsContext";
import { StatusBadge } from "@/components/StatusBadge";
import { useT } from "@/lib/i18n/LanguageContext";
import { ApiError, deleteJob, listJobs } from "@/lib/api";
import { formatRelative, humanize, shortId } from "@/lib/format";
import * as logBus from "@/lib/log-bus";
import type { JobStatus, JobSummary } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";

import styles from "./page.module.css";

// Canonical JobStatus values, in the order the dashboard lists them.
// The display label is resolved at render time via the translation
// dictionary (``statusLabels.<value>``); only the enum value is fixed.
const STATUS_OPTIONS: readonly JobStatus[] = [
  "pending_compliance",
  "accepted",
  "published",
  "rejected",
  "failed",
];

type StatusFilter = "all" | JobStatus;

export default function JobsListPage() {
  const t = useT();
  const { settings, hydrated } = useSettings();
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const announcedRef = useRef(false);
  const lastFilterRef = useRef<StatusFilter>("all");

  useEffect(() => {
    if (!announcedRef.current) {
      announcedRef.current = true;
      logBus.emit({
        source: "frontend",
        level: "info",
        message: "jobs list opened",
      });
    }
  }, []);

  useEffect(() => {
    if (lastFilterRef.current === statusFilter) return;
    lastFilterRef.current = statusFilter;
    logBus.emit({
      source: "frontend",
      level: "info",
      message: `jobs list status filter → ${statusFilter}`,
      meta: { status: statusFilter },
    });
  }, [statusFilter]);

  const loader = useCallback(
    (signal: AbortSignal) =>
      listJobs(
        {
          limit: 100,
          ...(statusFilter !== "all" ? { status: statusFilter } : {}),
        },
        signal,
      ),
    // reloadTick is included so a manual refresh after delete re-fetches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [reloadTick, statusFilter],
  );

  const { data, error, loading } = usePolling<JobSummary[]>(loader, {
    intervalMs: Math.max(1, settings.pollingIntervalSeconds) * 1000,
    enabled: hydrated && settings.autoPollingEnabled,
  });

  const handleDelete = async (jobId: string) => {
    setActionError(null);
    logBus.emit({
      source: "frontend",
      level: "info",
      message: `delete-job requested: ${shortId(jobId)}`,
      meta: { jobId },
    });
    try {
      await deleteJob(jobId);
      logBus.emit({
        source: "frontend",
        level: "success",
        message: `delete-job succeeded: ${shortId(jobId)}`,
        meta: { jobId },
      });
      setConfirmingId(null);
      setReloadTick((t) => t + 1);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      setActionError(`Delete failed: ${msg}`);
      logBus.emit({
        source: "frontend",
        level: "error",
        message: `delete-job failed: ${shortId(jobId)}`,
        meta: { jobId, error: msg },
      });
    }
  };

  return (
    <div>
      <header className={styles.header}>
        <h1>
          {t("jobs.title")}
          <HelpHint slug="jobs-list" />
        </h1>
        <Link href="/jobs/new" className="btn btn-primary">
          {t("jobs.newJob")}
        </Link>
      </header>

      <div className={styles.filterBar}>
        <label htmlFor="status-filter" className={styles.filterLabel}>
          {t("jobs.filterByStatus")}
        </label>
        <select
          id="status-filter"
          className={styles.filterSelect}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
        >
          <option value="all">{t("jobs.filterAll")}</option>
          {STATUS_OPTIONS.map((value) => (
            <option key={value} value={value}>
              {t(`statusLabels.${value}`)}
            </option>
          ))}
        </select>
        {data !== null && (
          <span className={styles.filterCount}>
            {data.length} {t("nav.jobs").toLowerCase()}
          </span>
        )}
      </div>

      {actionError && <ErrorMessage message={actionError} />}
      {error && (
        <ErrorMessage
          message={`${error.message}\nCheck Settings → Backend API Base URL.`}
          title={t("jobs.failedToLoad")}
        />
      )}
      {loading && data === null && !error && (
        <LoadingState label={t("jobs.loadingJobs")} />
      )}
      {data !== null && (
        <JobsTable
          jobs={data}
          statusFilter={statusFilter}
          confirmingId={confirmingId}
          onAskDelete={(id) => {
            setConfirmingId(id);
            setActionError(null);
          }}
          onCancelDelete={() => setConfirmingId(null)}
          onConfirmDelete={handleDelete}
        />
      )}
    </div>
  );
}

interface JobsTableProps {
  readonly jobs: readonly JobSummary[];
  readonly statusFilter: StatusFilter;
  readonly confirmingId: string | null;
  readonly onAskDelete: (jobId: string) => void;
  readonly onCancelDelete: () => void;
  readonly onConfirmDelete: (jobId: string) => Promise<void>;
}

function JobsTable({
  jobs,
  statusFilter,
  confirmingId,
  onAskDelete,
  onCancelDelete,
  onConfirmDelete,
}: JobsTableProps) {
  const t = useT();
  if (jobs.length === 0) {
    return (
      <div className="card">
        <p className="muted">
          {statusFilter === "all"
            ? t("dashboard.noJobsYet")
            : t("jobs.noJobs")}
        </p>
      </div>
    );
  }
  return (
    <div className="card">
      <div className={styles.tableScroll}>
        <table className="simple">
          <thead>
            <tr>
              <th>{t("jobs.title").replace(/s$/, "")}</th>
              <th>{t("jobs.status")}</th>
              <th>{t("jobs.voice")} / {t("jobs.face")}</th>
              <th>{t("jobs.progress")}</th>
              <th>{t("jobs.currentStage")}</th>
              <th>{t("dashboard.qc")}</th>
              <th>{t("dashboard.finalExport")}</th>
              <th>{t("jobs.artifacts")}</th>
              <th>{t("dashboard.updated")}</th>
              <th>{t("jobs.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td>
                  <Link href={`/jobs/${job.id}`} className={styles.jobLink}>
                    <strong>{shortId(job.id)}</strong>
                  </Link>
                  <div className={styles.brief} title={job.brief}>
                    {job.brief}
                  </div>
                </td>
                <td>
                  <StatusBadge status={job.status} />
                </td>
                <td className={styles.modeCol}>
                  <div>{humanize(job.voice_mode)}</div>
                  <div className="muted">
                    {job.face_mode ? humanize(job.face_mode) : t("common.noFace")}
                  </div>
                </td>
                <td className={styles.progressCol}>
                  <ProgressBar percent={job.progress_percent} />
                </td>
                <td>{job.current_stage ? humanize(job.current_stage) : "—"}</td>
                <td>
                  <QcCell qcPassed={job.qc_passed} />
                </td>
                <td>
                  <FinalExportCell available={job.final_export_available} />
                </td>
                <td>{job.artifact_count}</td>
                <td>{formatRelative(job.updated_at)}</td>
                <td>
                  {confirmingId === job.id ? (
                    <span className={styles.confirm}>
                      <span className={styles.confirmText}>
                        {t("jobs.confirmDelete")}
                      </span>
                      <button
                        type="button"
                        className={styles.btnDanger}
                        onClick={() => onConfirmDelete(job.id)}
                      >
                        {t("common.yes")}
                      </button>
                      <button
                        type="button"
                        className={styles.btnGhost}
                        onClick={onCancelDelete}
                      >
                        {t("common.no")}
                      </button>
                    </span>
                  ) : (
                    <span className={styles.actions}>
                      <Link
                        href={`/jobs/${job.id}`}
                        className={styles.actionLink}
                      >
                        {t("common.view")}
                      </Link>
                      {(job.can_edit ?? job.status !== "published") ? (
                        <Link
                          href={`/jobs/${job.id}/edit`}
                          className={styles.actionLink}
                        >
                          {t("common.edit")}
                        </Link>
                      ) : (
                        <span
                          className={`${styles.actionLink} ${styles.actionLinkDisabled}`}
                          title={t("editJob.cannotEditThisJob")}
                          aria-disabled="true"
                        >
                          {t("common.edit")}
                        </span>
                      )}
                      <button
                        type="button"
                        className={styles.actionDangerLink}
                        onClick={() => onAskDelete(job.id)}
                      >
                        {t("common.delete")}
                      </button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function QcCell({ qcPassed }: { readonly qcPassed: boolean | null | undefined }) {
  const t = useT();
  if (qcPassed === undefined || qcPassed === null) {
    return <span className={styles.qcPending}>{t("common.pending")}</span>;
  }
  return qcPassed ? (
    <span className={styles.qcPassed}>{t("common.passed")}</span>
  ) : (
    <span className={styles.qcFailed}>{t("common.failed")}</span>
  );
}

function FinalExportCell({ available }: { readonly available: boolean | undefined }) {
  const t = useT();
  return available ? (
    <span className={styles.exportReady}>{t("common.available")}</span>
  ) : (
    <span className={styles.exportPending}>{t("statusLabels.not_ready")}</span>
  );
}
