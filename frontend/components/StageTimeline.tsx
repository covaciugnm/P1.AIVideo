"use client";

import { formatDate, formatDurationMs } from "@/lib/format";
import { useT } from "@/lib/i18n/LanguageContext";
import { tStage } from "@/lib/i18n/formatters";
import type { StageProgress, StageTimelineEntry } from "@/lib/types";

import { StatusBadge } from "./StatusBadge";
import styles from "./StageTimeline.module.css";

interface StageTimelineProps {
  readonly stages: readonly StageProgress[];
  readonly timeline: readonly StageTimelineEntry[];
}

// Map canonical stage names to translation keys. Anything not in the
// map falls back to the humanised value (English) so the operator
// never sees a raw enum name.
const STAGE_TRANSLATION_KEY: Readonly<Record<string, string>> = {
  compliance: "stageLabels.compliance",
  identity_guard: "stageLabels.identity_guard",
  scriptwriter: "stageLabels.scriptwriter",
  voice: "stageLabels.voice",
  face: "stageLabels.face",
  pre_lipsync_auth: "stageLabels.pre_lipsync_auth",
  lipsync: "stageLabels.lipsync",
  editor: "stageLabels.editor",
  qc: "stageLabels.qc",
  publisher: "stageLabels.publisher",
  export_disclosure_validation: "stageLabels.export_disclosure_validation",
  policy_gate: "stageLabels.policy_gate",
};

export function StageTimeline({ stages, timeline }: StageTimelineProps) {
  const t = useT();
  const byStage = new Map<string, StageTimelineEntry>();
  for (const entry of timeline) byStage.set(entry.stage_name, entry);

  if (stages.length === 0) {
    return <p className={styles.muted}>{t("stageTimeline.noStages")}</p>;
  }

  return (
    <ol className={styles.list}>
      {stages.map((stage) => {
        const entry = byStage.get(stage.stage_name) ?? null;
        const errMsg = entry?.error_message ?? null;
        const refs = entry?.artifact_refs ?? [];
        const tKey = STAGE_TRANSLATION_KEY[stage.stage_name];
        // Prefer the legacy ``stageLabels.*`` mapping if present;
        // otherwise route through ``tStage`` which goes to the
        // ``stages.*`` section (also bilingual) and never hits raw
        // humanize.
        const stageLabel = tKey ? t(tKey) : tStage(t, stage.stage_name);
        return (
          <li key={stage.stage_name} className={styles.item}>
            <div className={styles.row}>
              <span
                className={styles.name}
                title={t("stageTimeline.currentStage")}
              >
                {stageLabel}
              </span>
              <StatusBadge status={stage.status} />
            </div>
            <div className={styles.meta}>
              {entry ? (
                <>
                  <span>
                    {t("stageTimeline.completedStages")}: {formatDate(entry.started_at)}
                  </span>
                  {entry.completed_at && (
                    <span>
                      {t("common.created")}: {formatDate(entry.completed_at)}
                    </span>
                  )}
                  {entry.duration_ms !== null && (
                    <span>
                      {t("common.duration")}: {formatDurationMs(entry.duration_ms)}
                    </span>
                  )}
                </>
              ) : (
                <span className={styles.muted}>{t("common.pending")}</span>
              )}
            </div>
            {refs.length > 0 && (
              <div className={styles.refs}>
                <span className={styles.refsLabel}>{t("jobs.artifacts")}:</span>
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
