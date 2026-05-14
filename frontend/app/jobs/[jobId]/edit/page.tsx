"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ErrorMessage } from "@/components/ErrorMessage";
import { LoadingState } from "@/components/LoadingState";
import { StatusBadge } from "@/components/StatusBadge";
import { ApiError, getJob, updateJob } from "@/lib/api";
import { isTerminalStatus, shortId } from "@/lib/format";
import * as logBus from "@/lib/log-bus";
import type { JobResponse, JobStatus } from "@/lib/types";

import styles from "./page.module.css";

export default function EditJobPage({
  params,
}: {
  readonly params: { readonly jobId: string };
}) {
  const { jobId } = params;
  const router = useRouter();

  const [job, setJob] = useState<JobResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const announcedRef = useRef(false);

  // Form fields.
  const [brief, setBrief] = useState("");
  const [duration, setDuration] = useState(30);
  const [scriptText, setScriptText] = useState("");

  useEffect(() => {
    if (!announcedRef.current) {
      announcedRef.current = true;
      logBus.emit({
        source: "frontend",
        level: "info",
        message: `edit job opened: ${shortId(jobId)}`,
        meta: { jobId },
      });
    }
    const controller = new AbortController();
    (async () => {
      try {
        const j = await getJob(jobId, controller.signal);
        setJob(j);
        setBrief(j.brief);
        setDuration(j.target_duration_seconds);
        setScriptText(j.script_text ?? "");
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        const msg = err instanceof Error ? err.message : String(err);
        setLoadError(msg);
      }
    })();
    return () => controller.abort();
  }, [jobId]);

  if (loadError) {
    return (
      <div>
        <Link href="/jobs" className="muted">
          ← Back to jobs
        </Link>
        <ErrorMessage message={loadError} title="Failed to load job" />
      </div>
    );
  }
  if (!job) {
    return <LoadingState label="Loading job…" />;
  }

  const status = job.status as JobStatus;
  const terminal = isTerminalStatus(status);
  const passedCompliance = status !== "pending_compliance";

  const briefChanged = brief !== job.brief;
  const durationChanged = duration !== job.target_duration_seconds;
  const scriptChanged = (scriptText || null) !== (job.script_text || null);
  const hasChanges = briefChanged || durationChanged || scriptChanged;
  const canSubmit = hasChanges && !submitting && !terminal;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);

    const patch: Record<string, unknown> = {};
    if (briefChanged) patch.brief = brief.trim();
    if (durationChanged) patch.target_duration_seconds = duration;
    if (scriptChanged) patch.script_text = scriptText.trim() || null;

    logBus.emit({
      source: "frontend",
      level: "info",
      message: `edit-job submitted: ${shortId(jobId)}`,
      meta: { jobId, fields: Object.keys(patch) },
    });

    try {
      const updated = await updateJob(jobId, patch);
      logBus.emit({
        source: "frontend",
        level: "success",
        message: `edit-job succeeded: ${shortId(jobId)}`,
        meta: { jobId, status: updated.status },
      });
      router.push(`/jobs/${jobId}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      setSubmitError(msg);
      setSubmitting(false);
      logBus.emit({
        source: "frontend",
        level: "error",
        message: `edit-job failed: ${shortId(jobId)}`,
        meta: { jobId, error: msg },
      });
    }
  };

  return (
    <div>
      <header className={styles.header}>
        <Link href={`/jobs/${jobId}`} className="muted">
          ← Back to job
        </Link>
        <h1 className={styles.title}>
          Edit job <code>{shortId(jobId)}</code>{" "}
          <StatusBadge status={status} />
        </h1>
      </header>

      {terminal && (
        <div className="card">
          <p className="muted">
            This job is in a terminal state ({status}). Editing is disabled —
            create a new job with the desired metadata instead.
          </p>
        </div>
      )}

      {!terminal && passedCompliance && (
        <div className="compliance-banner">
          Compliance gate has run. Voice / face / compliance flags / script
          text edits are locked because later stages may have consumed them.
          You can still edit the brief and target duration.
        </div>
      )}

      <form className={styles.form} onSubmit={handleSubmit}>
        <section className="card">
          <h2>Editable</h2>
          <div className="field">
            <label htmlFor="brief">Brief</label>
            <textarea
              id="brief"
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              maxLength={2000}
              disabled={terminal}
              required
            />
            <span className={styles.muted}>{brief.length} / 2000</span>
          </div>
          <div className="field">
            <label htmlFor="duration">Target duration (seconds)</label>
            <input
              id="duration"
              type="number"
              min={15}
              max={60}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              disabled={terminal}
            />
          </div>
          {!passedCompliance && (
            <div className="field">
              <label htmlFor="script">Script text</label>
              <textarea
                id="script"
                value={scriptText}
                onChange={(e) => setScriptText(e.target.value)}
                maxLength={8000}
                disabled={terminal}
              />
              <span className={styles.muted}>
                {scriptText.length} / 8000
              </span>
            </div>
          )}
        </section>

        <section className="card">
          <h2>Read-only</h2>
          <dl className="kv">
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
          </dl>
        </section>

        {submitError && (
          <ErrorMessage message={submitError} title="Update rejected" />
        )}

        <div className={styles.actions}>
          <Link href={`/jobs/${jobId}`} className="btn btn-ghost">
            Cancel
          </Link>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!canSubmit}
          >
            {submitting ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </div>
  );
}
