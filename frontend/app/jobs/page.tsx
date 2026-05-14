"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ErrorMessage } from "@/components/ErrorMessage";
import { LoadingState } from "@/components/LoadingState";
import { ProgressBar } from "@/components/ProgressBar";
import { useSettings } from "@/components/SettingsContext";
import { StatusBadge } from "@/components/StatusBadge";
import { ApiError, deleteJob, listJobs } from "@/lib/api";
import { formatRelative, humanize, shortId } from "@/lib/format";
import * as logBus from "@/lib/log-bus";
import type { JobSummary } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";

import styles from "./page.module.css";

export default function JobsListPage() {
  const { settings, hydrated } = useSettings();
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const announcedRef = useRef(false);

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

  const loader = useCallback(
    (signal: AbortSignal) => listJobs({ limit: 100 }, signal),
    // reloadTick is included so a manual refresh after delete re-fetches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [reloadTick],
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
        <h1>Jobs</h1>
        <Link href="/jobs/new" className="btn btn-primary">
          + New job
        </Link>
      </header>

      {actionError && <ErrorMessage message={actionError} />}
      {error && (
        <ErrorMessage
          message={`${error.message}\nCheck Settings → Backend API Base URL.`}
          title="Failed to load jobs"
        />
      )}
      {loading && data === null && !error && <LoadingState label="Loading jobs…" />}
      {data !== null && (
        <JobsTable
          jobs={data}
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
  readonly confirmingId: string | null;
  readonly onAskDelete: (jobId: string) => void;
  readonly onCancelDelete: () => void;
  readonly onConfirmDelete: (jobId: string) => Promise<void>;
}

function JobsTable({
  jobs,
  confirmingId,
  onAskDelete,
  onCancelDelete,
  onConfirmDelete,
}: JobsTableProps) {
  if (jobs.length === 0) {
    return (
      <div className="card">
        <p className="muted">No jobs yet. Create one to get started.</p>
      </div>
    );
  }
  return (
    <div className="card">
      <div className={styles.tableScroll}>
        <table className="simple">
          <thead>
            <tr>
              <th>Job</th>
              <th>Status</th>
              <th>Voice / Face</th>
              <th>Progress</th>
              <th>Current stage</th>
              <th>Duration</th>
              <th>Artifacts</th>
              <th>Updated</th>
              <th>Actions</th>
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
                    {job.face_mode ? humanize(job.face_mode) : "no face"}
                  </div>
                </td>
                <td className={styles.progressCol}>
                  <ProgressBar percent={job.progress_percent} />
                </td>
                <td>{job.current_stage ? humanize(job.current_stage) : "—"}</td>
                <td>{job.target_duration_seconds}s</td>
                <td>{job.artifact_count}</td>
                <td>{formatRelative(job.updated_at)}</td>
                <td>
                  {confirmingId === job.id ? (
                    <span className={styles.confirm}>
                      <span className={styles.confirmText}>Delete?</span>
                      <button
                        type="button"
                        className={styles.btnDanger}
                        onClick={() => onConfirmDelete(job.id)}
                      >
                        Yes
                      </button>
                      <button
                        type="button"
                        className={styles.btnGhost}
                        onClick={onCancelDelete}
                      >
                        No
                      </button>
                    </span>
                  ) : (
                    <span className={styles.actions}>
                      <Link
                        href={`/jobs/${job.id}`}
                        className={styles.actionLink}
                      >
                        View
                      </Link>
                      <Link
                        href={`/jobs/${job.id}/edit`}
                        className={styles.actionLink}
                      >
                        Edit
                      </Link>
                      <button
                        type="button"
                        className={styles.actionDangerLink}
                        onClick={() => onAskDelete(job.id)}
                      >
                        Delete
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
