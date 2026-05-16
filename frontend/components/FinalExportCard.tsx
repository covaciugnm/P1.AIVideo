"use client";

import { formatDate, shortHash } from "@/lib/format";
import { useT } from "@/lib/i18n/LanguageContext";
import type { FinalExportResponse } from "@/lib/types";

import { StatusBadge } from "./StatusBadge";
import styles from "./FinalExportCard.module.css";

interface FinalExportCardProps {
  readonly response: FinalExportResponse;
}

export function FinalExportCard({ response }: FinalExportCardProps) {
  const t = useT();
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
        <h3>{t("finalExportLabels.title")}</h3>
        <StatusBadge status={m.status} />
        <StatusBadge status={m.passed_qc ? "pass" : "fail"} title={t("badges.qcGate")} />
        <StatusBadge
          status={m.disclosure_status}
          title={t("badges.aiDisclosureStatus")}
        />
        <StatusBadge
          status={exportIsPlaceholder ? "manifest-only" : "real-mp4"}
          title={exportIsPlaceholder ? t("badges.manifestOnly") : t("badges.realMp4")}
        />
      </div>
      <dl className="kv">
        <dt>{t("finalExportLabels.exportUri")}</dt>
        <dd>
          <code>{m.export_uri}</code>
        </dd>
        <dt>{t("finalExportLabels.exportType")}</dt>
        <dd>
          {m.export_type} ({m.mime_type})
        </dd>
        <dt>{t("finalExportLabels.targetDuration")}</dt>
        <dd>{m.target_duration_seconds.toFixed(2)} s</dd>
        <dt>{t("finalExportLabels.watermarkRequired")}</dt>
        <dd>{m.watermark_required ? t("common.yes") : t("common.no")}</dd>
        <dt>{t("finalExportLabels.c2paRequired")}</dt>
        <dd>{m.c2pa_required ? t("common.yes") : t("common.no")}</dd>
        <dt>{t("finalExportLabels.reelDraft")}</dt>
        <dd title={m.source_reel_draft_uri}>
          <code>{shortHash(m.source_reel_draft_checksum)}</code>
        </dd>
        <dt>{t("finalExportLabels.qcReport")}</dt>
        <dd title={m.qc_report_uri}>
          <code>{shortHash(m.qc_report_checksum)}</code>
        </dd>
        <dt>{t("jobs.created")}</dt>
        <dd>{formatDate(response.created_at)}</dd>
      </dl>
      <p className={styles.note}>{t("finalExportLabels.note")}</p>
      {(exportIsPlaceholder || reelDraftIsPlaceholder) && (
        <p className={styles.note} role="note">
          <strong>{t("finalExportLabels.noEncodedVideoNote")}</strong>
        </p>
      )}
    </div>
  );
}
