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
  const clamped = Math.max(0, Math.min(100, percent));
  const hasFailure = (failedStages ?? 0) > 0;
  return (
    <div className={styles.wrapper} aria-label="Progress">
      <div className={styles.track} role="progressbar" aria-valuenow={Math.round(clamped)} aria-valuemin={0} aria-valuemax={100}>
        <div
          className={hasFailure ? styles.barDanger : styles.bar}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <div className={styles.label}>
        <span>{Math.round(clamped)}%</span>
        {completedStages !== undefined && totalStages !== undefined && (
          <span className={styles.muted}>
            {completedStages} / {totalStages} stages
            {hasFailure ? ` (${failedStages ?? 0} failed)` : ""}
          </span>
        )}
      </div>
    </div>
  );
}
