"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { ErrorMessage } from "@/components/ErrorMessage";
import { HelpHint } from "@/components/HelpHint";
import { LoadingState } from "@/components/LoadingState";
import { ProgressBar } from "@/components/ProgressBar";
import { useSettings } from "@/components/SettingsContext";
import { StatusBadge } from "@/components/StatusBadge";
import { listJobs } from "@/lib/api";
import { formatRelative, humanize, shortId } from "@/lib/format";
import { useT } from "@/lib/i18n/LanguageContext";
import * as logBus from "@/lib/log-bus";
import type { JobSummary } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";

import styles from "./page.module.css";

export default function DashboardPage() {
  const { settings, hydrated } = useSettings();
  const t = useT();
  const announcedRef = useRef(false);

  useEffect(() => {
    if (!announcedRef.current) {
      announcedRef.current = true;
      logBus.emit({
        source: "frontend",
        level: "info",
        message: "dashboard opened",
      });
    }
  }, []);

  const { data, error, loading } = usePolling<JobSummary[]>(
    (signal) => listJobs({ limit: 50 }, signal),
    {
      intervalMs: Math.max(1, settings.pollingIntervalSeconds) * 1000,
      enabled: hydrated && settings.autoPollingEnabled,
    },
  );

  return (
    <div>
      <header className={styles.header}>
        <h1>
          {t("dashboard.title")}
          <HelpHint slug="dashboard" />
        </h1>
        <Link href="/jobs/new" className="btn btn-primary">
          {t("dashboard.newJob")}
        </Link>
      </header>
      {error && (
        <ErrorMessage
          message={`${error.message}\nCheck Settings → Backend API Base URL.`}
          title={t("jobs.failedToLoad")}
        />
      )}
      {loading && data === null && !error && (
        <LoadingState label={t("common.loading")} />
      )}
      {data !== null && <JobsTable jobs={data} />}
    </div>
  );
}

function JobsTable({ jobs }: { readonly jobs: readonly JobSummary[] }) {
  const t = useT();
  if (jobs.length === 0) {
    return (
      <div className="card">
        <p className="muted">{t("dashboard.noJobsYet")}</p>
      </div>
    );
  }
  return (
    <div className="card">
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
                {job.qc_passed === undefined || job.qc_passed === null ? (
                  <span className={styles.qcPending}>{t("common.pending")}</span>
                ) : job.qc_passed ? (
                  <span className={styles.qcPassed}>{t("common.passed")}</span>
                ) : (
                  <span className={styles.qcFailed}>{t("common.failed")}</span>
                )}
              </td>
              <td>
                {job.final_export_available ? (
                  <span className={styles.exportReady}>{t("common.available")}</span>
                ) : (
                  <span className={styles.exportPending}>{t("statusLabels.not_ready")}</span>
                )}
              </td>
              <td>{job.artifact_count}</td>
              <td>{formatRelative(job.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
