"use client";

import { formatDate, shortHash } from "@/lib/format";
import { useT } from "@/lib/i18n/LanguageContext";
import type { QCReportResponse } from "@/lib/types";

import { StatusBadge } from "./StatusBadge";
import styles from "./QcReportCard.module.css";

interface QcReportCardProps {
  readonly report: QCReportResponse;
}

export function QcReportCard({ report }: QcReportCardProps) {
  const t = useT();
  const r = report.qc_report;
  // Phase 9D — distinguish a metadata-only reel_draft (placeholder URI)
  // from a real one so the operator can tell at a glance whether the
  // QC checks ran against real media or only against the structural
  // metadata graph.
  const reelDraftIsPlaceholder = r.reel_draft_artifact_uri.startsWith(
    "placeholder://",
  );
  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <h3>{t("jobDetail.qcReport")}</h3>
        <StatusBadge status={r.passed ? "pass" : "fail"} />
        <StatusBadge
          status={reelDraftIsPlaceholder ? "metadata-only" : "real-media"}
          title={
            reelDraftIsPlaceholder
              ? t("qc.metadataOnlyNote")
              : t("qc.realMediaNote")
          }
        />
      </div>
      <dl className="kv">
        <dt>{t("qc.targetDuration")}</dt>
        <dd>{r.target_duration_seconds.toFixed(2)} s</dd>
        <dt>{t("qc.segments")}</dt>
        <dd>
          {r.segment_count} ({r.expected_segments.join(", ")})
        </dd>
        <dt>{t("qc.script")}</dt>
        <dd title={r.script_artifact_uri}>
          <code>{shortHash(r.script_artifact_checksum)}</code>
        </dd>
        <dt>{t("qc.editPlan")}</dt>
        <dd title={r.edit_plan_artifact_uri}>
          <code>{shortHash(r.edit_plan_artifact_checksum)}</code>
        </dd>
        <dt>{t("qc.reelDraftUri")}</dt>
        <dd>
          <code>{r.reel_draft_artifact_uri}</code>
        </dd>
        <dt>{t("jobs.created")}</dt>
        <dd>{formatDate(report.created_at)}</dd>
      </dl>
      <h4 className={styles.checksHeading}>{t("qc.checksHeading")}</h4>
      <ul className={styles.checks}>
        {r.checks.map((c) => (
          <li key={c.name} className={styles.check}>
            <div className={styles.checkRow}>
              <span className={styles.checkName}>{c.name}</span>
              <StatusBadge status={c.decision} />
            </div>
            {c.detail && <p className={styles.detail}>{c.detail}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
