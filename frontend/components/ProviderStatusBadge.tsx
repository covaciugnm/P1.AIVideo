"use client";

// Phase 12 — universal provider status indicator (green/red/yellow dot).
// Used by every dropdown that lists a provider so the operator can see
// whether the selected backend is ready without opening Settings.

import type { ProviderStatus } from "@/lib/types";
import { useT } from "@/lib/i18n/LanguageContext";

import styles from "./ProviderStatusBadge.module.css";

const VARIANT: Readonly<Record<ProviderStatus, string>> = {
  available: "ok",
  configured: "warn",
  not_configured: "bad",
  not_implemented: "bad",
  disabled: "bad",
  error: "bad",
};

export function ProviderStatusBadge({
  status,
  label,
  notes,
  inline = false,
}: {
  readonly status: ProviderStatus;
  readonly label?: string;
  readonly notes?: string;
  readonly inline?: boolean;
}) {
  const t = useT();
  const variant = VARIANT[status] ?? "bad";
  const fallbackLabel = t(`providerStatus.${status}`);
  const title = notes ? `${label ?? fallbackLabel} — ${notes}` : label ?? fallbackLabel;
  return (
    <span
      className={`${styles.badge} ${styles[variant]} ${inline ? styles.inline : ""}`}
      role="status"
      aria-label={title}
      title={title}
    >
      <span className={`${styles.dot} ${styles[`dot-${variant}`]}`} aria-hidden />
      {label ?? fallbackLabel}
    </span>
  );
}
