"use client";

import Link from "next/link";

import { ErrorMessage } from "@/components/ErrorMessage";
import { LoadingState } from "@/components/LoadingState";
import { ProgressBar } from "@/components/ProgressBar";
import { StatusBadge } from "@/components/StatusBadge";
import { listJobs } from "@/lib/api";
import { formatRelative, humanize, shortId } from "@/lib/format";
import type { JobSummary } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";

import styles from "./page.module.css";

export default function DashboardPage() {
  const { data, error, loading } = usePolling<JobSummary[]>(
    (signal) => listJobs({ limit: 50 }, signal),
    { intervalMs: 5_000 },
  );

  return (
    <div>
      <header className={styles.header}>
        <h1>Jobs</h1>
        <Link href="/jobs/new" className="btn btn-primary">
          + New job
        </Link>
      </header>
      {error && (
        <ErrorMessage
          message={error.message}
          title="Failed to load jobs"
        />
      )}
      {loading && data === null && <LoadingState label="Loading jobs…" />}
      {data !== null && <JobsTable jobs={data} />}
    </div>
  );
}

function JobsTable({ jobs }: { readonly jobs: readonly JobSummary[] }) {
  if (jobs.length === 0) {
    return (
      <div className="card">
        <p className="muted">No jobs yet. Create one to get started.</p>
      </div>
    );
  }
  return (
    <div className="card">
      <table className="simple">
        <thead>
          <tr>
            <th>Job</th>
            <th>Status</th>
            <th>Voice / Face</th>
            <th>Progress</th>
            <th>Current stage</th>
            <th>Artifacts</th>
            <th>Updated</th>
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
              <td>{job.artifact_count}</td>
              <td>{formatRelative(job.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
