"use client";

import { useT } from "@/lib/i18n/LanguageContext";

import styles from "./ProgressBar.module.css";

interface ProgressBarProps {
  readonly percent: number;
  readonly completedStages?: number;
  readonly totalStages?: number;
  readonly failedStages?: number;
}

export function ProgressBar({
  percent,
  completedStages,
  totalStages,
  failedStages,
}: ProgressBarProps) {
  const t = useT();
  const clamped = Math.max(0, Math.min(100, percent));
  const failed = failedStages ?? 0;
  const hasFailure = failed > 0;
  return (
    <div className={styles.wrapper} aria-label={t("progressBar.ariaLabel")}>
      <div
        className={styles.track}
        role="progressbar"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={hasFailure ? styles.barDanger : styles.bar}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <div className={styles.label}>
        <span>{Math.round(clamped)}%</span>
        {completedStages !== undefined && totalStages !== undefined && (
          <span className={styles.muted}>
            {t("progressBar.stagesUnit", {
              completed: completedStages,
              total: totalStages,
            })}
            {hasFailure ? t("progressBar.failedSuffix", { count: failed }) : ""}
          </span>
        )}
      </div>
    </div>
  );
}
