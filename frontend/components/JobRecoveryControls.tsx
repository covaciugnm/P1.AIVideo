"use client";

import { useState } from "react";

import { cancelJob, retryJob } from "@/lib/api";
import * as logBus from "@/lib/log-bus";
import type { JobDetail } from "@/lib/types";

import styles from "./JobRecoveryControls.module.css";

interface JobRecoveryControlsProps {
  readonly job: JobDetail;
  readonly onMutated: () => void;
}

const _TERMINAL = new Set(["published", "rejected", "failed"]);
const _RETRYABLE = new Set(["failed", "rejected"]);

export function JobRecoveryControls({
  job,
  onMutated,
}: JobRecoveryControlsProps) {
  const [busy, setBusy] = useState<"cancel" | "retry" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canCancel = !_TERMINAL.has(job.status);
  const canRetry = _RETRYABLE.has(job.status);
  const recovery = job.recovery_metadata ?? {};
  const retryCount = (recovery["retry_count"] as number | undefined) ?? 0;
  const cancelledAt = recovery["cancelled_at"] as string | undefined;
  const cancellationReason = recovery["cancellation_reason"] as
    | string
    | undefined;
  const retryRequestedAt = recovery["retry_requested_at"] as string | undefined;

  const handleCancel = async () => {
    const reason = window.prompt(
      "Cancel this job? Optional reason:",
      "operator cancelled",
    );
    if (reason === null) return; // user closed the prompt
    setBusy("cancel");
    setError(null);
    try {
      const updated = await cancelJob(job.id, { reason: reason || null });
      logBus.emit({
        source: "frontend",
        level: "info",
        message: `job ${job.id} cancelled`,
        meta: { reason },
      });
      onMutated();
      // Hint at the new status without forcing a re-render — onMutated
      // triggers the parent's reload.
      void updated;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`cancel failed: ${msg}`);
      logBus.emit({
        source: "frontend",
        level: "warning",
        message: `job ${job.id} cancel failed`,
        meta: { error: msg },
      });
    } finally {
      setBusy(null);
    }
  };

  const handleRetry = async () => {
    if (
      !window.confirm(
        "Mark this job for retry? The orchestrator will pick it up on the next worker pass.",
      )
    ) {
      return;
    }
    setBusy("retry");
    setError(null);
    try {
      await retryJob(job.id, {});
      logBus.emit({
        source: "frontend",
        level: "info",
        message: `job ${job.id} retry requested`,
      });
      onMutated();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`retry failed: ${msg}`);
      logBus.emit({
        source: "frontend",
        level: "warning",
        message: `job ${job.id} retry failed`,
        meta: { error: msg },
      });
    } finally {
      setBusy(null);
    }
  };

  if (!canCancel && !canRetry && !cancelledAt && retryCount === 0) {
    return null;
  }

  return (
    <section className="card">
      <h2>Recovery controls</h2>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.btn}
          disabled={!canCancel || busy !== null}
          onClick={handleCancel}
        >
          {busy === "cancel" ? "Cancelling…" : "Cancel job"}
        </button>
        <button
          type="button"
          className={styles.btn}
          disabled={!canRetry || busy !== null}
          onClick={handleRetry}
        >
          {busy === "retry" ? "Requesting retry…" : "Retry job"}
        </button>
        {!canCancel && (
          <span className={styles.note}>
            Job is in a terminal state — cancel disabled.
          </span>
        )}
        {!canRetry && _TERMINAL.has(job.status) && job.status !== "failed" && job.status !== "rejected" && (
          <span className={styles.note}>
            Retry only available for failed / rejected jobs.
          </span>
        )}
      </div>
      {error && <p className={styles.err}>{error}</p>}
      {(cancelledAt || retryCount > 0) && (
        <dl className={styles.metaList}>
          {cancelledAt && (
            <>
              <dt>Cancelled at</dt>
              <dd>{cancelledAt}</dd>
            </>
          )}
          {cancellationReason && (
            <>
              <dt>Cancellation reason</dt>
              <dd>{cancellationReason}</dd>
            </>
          )}
          {retryRequestedAt && (
            <>
              <dt>Retry requested at</dt>
              <dd>{retryRequestedAt}</dd>
            </>
          )}
          {retryCount > 0 && (
            <>
              <dt>Retry count</dt>
              <dd>{retryCount}</dd>
            </>
          )}
        </dl>
      )}
      <p className={styles.smallPrint}>
        Phase 8D limitation: cancel marks the job rejected but cannot
        kill a stage that is already running on a worker. Retry records
        operator intent; the worker pipeline picks it up at the next
        pass.
      </p>
    </section>
  );
}
