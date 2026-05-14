import { formatDate, shortHash } from "@/lib/format";
import type { QCReportResponse } from "@/lib/types";

import { StatusBadge } from "./StatusBadge";
import styles from "./QcReportCard.module.css";

interface QcReportCardProps {
  readonly report: QCReportResponse;
}

export function QcReportCard({ report }: QcReportCardProps) {
  const r = report.qc_report;
  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <h3>QC Report</h3>
        <StatusBadge status={r.passed ? "pass" : "fail"} />
      </div>
      <dl className="kv">
        <dt>Target duration</dt>
        <dd>{r.target_duration_seconds.toFixed(2)} s</dd>
        <dt>Segments</dt>
        <dd>
          {r.segment_count} ({r.expected_segments.join(", ")})
        </dd>
        <dt>Script</dt>
        <dd title={r.script_artifact_uri}>
          <code>{shortHash(r.script_artifact_checksum)}</code>
        </dd>
        <dt>Edit plan</dt>
        <dd title={r.edit_plan_artifact_uri}>
          <code>{shortHash(r.edit_plan_artifact_checksum)}</code>
        </dd>
        <dt>Reel draft URI</dt>
        <dd>
          <code>{r.reel_draft_artifact_uri}</code>
        </dd>
        <dt>Created</dt>
        <dd>{formatDate(report.created_at)}</dd>
      </dl>
      <h4 className={styles.checksHeading}>Checks</h4>
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
