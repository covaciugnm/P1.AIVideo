import { humanize } from "@/lib/format";

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

export function StatusBadge({ status, title }: StatusBadgeProps) {
  const variant: Variant = STATUS_VARIANT[status] ?? "muted";
  return (
    <span
      className={`${styles.badge} ${styles[variant]}`}
      title={title ?? humanize(status)}
    >
      {humanize(status)}
    </span>
  );
}
