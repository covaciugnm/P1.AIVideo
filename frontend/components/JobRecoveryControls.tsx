"use client";

import { useState } from "react";

import { cancelJob, retryJob } from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageContext";
import * as logBus from "@/lib/log-bus";
import type { JobDetail } from "@/lib/types";

import { HelpHint } from "./HelpHint";
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
  const t = useT();
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
      t("jobDetail.cancelReason"),
      t("jobDetail.cancelReasonPlaceholder"),
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
    if (!window.confirm(t("recovery.retryAvailable"))) {
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
      <h2>{t("jobDetail.recoveryControls")} <HelpHint slug="recovery-controls" small /></h2>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.btn}
          disabled={!canCancel || busy !== null}
          onClick={handleCancel}
        >
          {busy === "cancel" ? t("jobDetail.cancelling") : t("jobDetail.cancelJob")}
        </button>
        <button
          type="button"
          className={styles.btn}
          disabled={!canRetry || busy !== null}
          onClick={handleRetry}
        >
          {busy === "retry" ? t("jobDetail.retrying") : t("jobDetail.retryJob")}
        </button>
        {!canCancel && (
          <span className={styles.note}>
            {t("recovery.terminalCancelDisabled")}
          </span>
        )}
        {!canRetry && _TERMINAL.has(job.status) && job.status !== "failed" && job.status !== "rejected" && (
          <span className={styles.note}>
            {t("recovery.terminalRetryDisabled")}
          </span>
        )}
      </div>
      {error && <p className={styles.err}>{error}</p>}
      {(cancelledAt || retryCount > 0) && (
        <dl className={styles.metaList}>
          {cancelledAt && (
            <>
              <dt>{t("recoveryHistory.cancelledAt")}</dt>
              <dd>{cancelledAt}</dd>
            </>
          )}
          {cancellationReason && (
            <>
              <dt>{t("recoveryHistory.cancellationReason")}</dt>
              <dd>{cancellationReason}</dd>
            </>
          )}
          {retryRequestedAt && (
            <>
              <dt>{t("recoveryHistory.retryRequestedAt")}</dt>
              <dd>{retryRequestedAt}</dd>
            </>
          )}
          {retryCount > 0 && (
            <>
              <dt>{t("recoveryHistory.retryCount")}</dt>
              <dd>{retryCount}</dd>
            </>
          )}
        </dl>
      )}
    </section>
  );
}
