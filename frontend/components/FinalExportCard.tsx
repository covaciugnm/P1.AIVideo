import { formatDate, shortHash } from "@/lib/format";
import type { FinalExportResponse } from "@/lib/types";

import { StatusBadge } from "./StatusBadge";
import styles from "./FinalExportCard.module.css";

interface FinalExportCardProps {
  readonly response: FinalExportResponse;
}

export function FinalExportCard({ response }: FinalExportCardProps) {
  const m = response.final_export;
  // Phase 9D — the publisher emits a placeholder export URI when the
  // upstream reel_draft is metadata-only. Distinguish that here so the
  // operator doesn't think a real MP4 was produced.
  const exportIsPlaceholder = m.export_uri.startsWith("placeholder://");
  const reelDraftIsPlaceholder = m.source_reel_draft_uri.startsWith(
    "placeholder://",
  );
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
        <StatusBadge
          status={exportIsPlaceholder ? "manifest-only" : "real-mp4"}
          title={
            exportIsPlaceholder
              ? "No real MP4 was encoded — manifest only"
              : "Real MP4 export claimed"
          }
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
        This is the metadata-only export-decision manifest (Phase 3J / 4B).
        A real packaged MP4 lives as a separate <code>final_export</code> artifact
        when the operator triggers <code>POST /api/v1/export/finalize</code>
        (Phase 8B); the Video preview card below renders that MP4 if present.
        Watermark + C2PA signing remain pending.
      </p>
      {(exportIsPlaceholder || reelDraftIsPlaceholder) && (
        <p className={styles.note} role="note">
          <strong>No real video was encoded.</strong>{" "}
          The upstream reel draft is metadata-only — either no real video
          provider ran (e.g. SadTalker not configured) or the operator
          uploaded no media. Configure a video provider or upload audio +
          image to produce a real MP4.
        </p>
      )}
    </div>
  );
}
