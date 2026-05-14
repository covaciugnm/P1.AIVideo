import { formatDate, shortHash } from "@/lib/format";
import type { FinalExportResponse } from "@/lib/types";

import { StatusBadge } from "./StatusBadge";
import styles from "./FinalExportCard.module.css";

interface FinalExportCardProps {
  readonly response: FinalExportResponse;
}

export function FinalExportCard({ response }: FinalExportCardProps) {
  const m = response.final_export;
  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <h3>Final Export</h3>
        <StatusBadge status={m.status} />
        <StatusBadge status={m.passed_qc ? "pass" : "fail"} title="QC gate" />
        <StatusBadge
          status={m.disclosure_status}
          title="AI-content disclosure status"
        />
      </div>
      <dl className="kv">
        <dt>Export URI</dt>
        <dd>
          <code>{m.export_uri}</code>
        </dd>
        <dt>Export type</dt>
        <dd>
          {m.export_type} ({m.mime_type})
        </dd>
        <dt>Target duration</dt>
        <dd>{m.target_duration_seconds.toFixed(2)} s</dd>
        <dt>Watermark required</dt>
        <dd>{String(m.watermark_required)}</dd>
        <dt>C2PA required</dt>
        <dd>{String(m.c2pa_required)}</dd>
        <dt>Reel draft</dt>
        <dd title={m.source_reel_draft_uri}>
          <code>{shortHash(m.source_reel_draft_checksum)}</code>
        </dd>
        <dt>QC report</dt>
        <dd title={m.qc_report_uri}>
          <code>{shortHash(m.qc_report_checksum)}</code>
        </dd>
        <dt>Created</dt>
        <dd>{formatDate(response.created_at)}</dd>
      </dl>
      <p className={styles.note}>
        Phase 4B: no real video is written and nothing is uploaded externally.
        This manifest is the metadata-only operator-visible export decision.
      </p>
    </div>
  );
}
