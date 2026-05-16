"use client";

import { humanize } from "@/lib/format";
import { useT } from "@/lib/i18n/LanguageContext";

import styles from "./StatusBadge.module.css";

type Variant = "info" | "success" | "warn" | "danger" | "muted";

const STATUS_VARIANT: Readonly<Record<string, Variant>> = {
  pending_compliance: "info",
  accepted: "info",
  published: "success",
  rejected: "danger",
  failed: "danger",

  pending: "muted",
  running: "info",
  succeeded: "success",
  skipped: "muted",
  warn: "warn",
  pass: "success",
  fail: "danger",

  accept: "success",
  reject: "danger",

  embedded: "success",
  missing: "danger",

  ok: "success",
  missing_assets: "warn",
  not_configured: "muted",
  not_implemented: "muted",
  error: "danger",
};

interface StatusBadgeProps {
  readonly status: string;
  readonly title?: string;
}

// Map of status / decision codes to the namespace + key that translates
// them. Job-level statuses go to ``statusLabels.*``; QC decisions and
// other reused tokens fall back to ``common.*``.
const TRANSLATION_KEY: Readonly<Record<string, string>> = {
  pending_compliance: "statusLabels.pending_compliance",
  accepted: "statusLabels.accepted",
  published: "statusLabels.published",
  rejected: "statusLabels.rejected",
  failed: "statusLabels.failed",
  succeeded: "statusLabels.succeeded",
  running: "statusLabels.running",
  skipped: "statusLabels.skipped",
  pending: "statusLabels.pending",
  available: "statusLabels.available",
  not_ready: "statusLabels.not_ready",
  pass: "common.passed",
  fail: "common.failed",
  warn: "common.warn",
  ok: "common.ok",
  missing_assets: "common.assetsMissing",
  not_configured: "common.notConfigured",
  not_implemented: "common.notImplemented",
  error: "common.error",
  // Disclosure / accept / reject — kept as ``common.*``.
  accept: "common.yes",
  reject: "common.no",
  embedded: "common.yes",
  missing: "common.no",
  // Phase 11A — extra QC / final-export markers used by the QcReportCard.
  "metadata-only": "common.metadataOnly",
  "real-media": "common.realMedia",
  "manifest-only": "badges.manifestOnly",
  "real-mp4": "badges.realMp4",
};

export function StatusBadge({ status, title }: StatusBadgeProps) {
  const t = useT();
  const variant: Variant = STATUS_VARIANT[status] ?? "muted";
  const key = TRANSLATION_KEY[status];
  // Resolve via the translation dictionary when we have a known key;
  // otherwise fall back to the stringified status (humanised) so the
  // UI never shows a raw enum value.
  const label = key ? t(key) : humanize(status);
  return (
    <span
      className={`${styles.badge} ${styles[variant]}`}
      title={title ?? label}
    >
      {label}
    </span>
  );
}
