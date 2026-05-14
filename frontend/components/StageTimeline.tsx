import { formatDate, formatDurationMs, humanize } from "@/lib/format";
import type { StageProgress, StageTimelineEntry } from "@/lib/types";

import { StatusBadge } from "./StatusBadge";
import styles from "./StageTimeline.module.css";

interface StageTimelineProps {
  readonly stages: readonly StageProgress[];
  readonly timeline: readonly StageTimelineEntry[];
}

export function StageTimeline({ stages, timeline }: StageTimelineProps) {
  const byStage = new Map<string, StageTimelineEntry>();
  for (const entry of timeline) byStage.set(entry.stage_name, entry);

  return (
    <ol className={styles.list}>
      {stages.map((stage) => {
        const entry = byStage.get(stage.stage_name) ?? null;
        const errMsg = entry?.error_message ?? null;
        const refs = entry?.artifact_refs ?? [];
        return (
          <li key={stage.stage_name} className={styles.item}>
            <div className={styles.row}>
              <span className={styles.name}>{humanize(stage.stage_name)}</span>
              <StatusBadge status={stage.status} />
            </div>
            <div className={styles.meta}>
              {entry ? (
                <>
                  <span>Started: {formatDate(entry.started_at)}</span>
                  {entry.completed_at && (
                    <span>Completed: {formatDate(entry.completed_at)}</span>
                  )}
                  {entry.duration_ms !== null && (
                    <span>Duration: {formatDurationMs(entry.duration_ms)}</span>
                  )}
                </>
              ) : (
                <span className={styles.muted}>Not started yet.</span>
              )}
            </div>
            {refs.length > 0 && (
              <div className={styles.refs}>
                <span className={styles.refsLabel}>Outputs:</span>
                {refs.map((ref) => (
                  <code key={ref} className={styles.refChip}>
                    {ref}
                  </code>
                ))}
              </div>
            )}
            {errMsg && <div className={styles.error}>{errMsg}</div>}
          </li>
        );
      })}
    </ol>
  );
}
