"use client";

import { useLanguage, useT } from "@/lib/i18n/LanguageContext";
import { LANGUAGE_META, SUPPORTED_LANGUAGE_CODES } from "@/lib/i18n/types";

export function LanguageSwitcher({
  className,
  compact = false,
}: {
  readonly className?: string;
  readonly compact?: boolean;
}) {
  const { language, setLanguage } = useLanguage();
  const t = useT();
  const label = t("badges.interfaceLanguage");
  return (
    <select
      className={className}
      value={language}
      onChange={(e) =>
        setLanguage(e.target.value as (typeof SUPPORTED_LANGUAGE_CODES)[number])
      }
      aria-label={label}
      title={label}
      style={
        compact
          ? {
              padding: "4px 6px",
              fontSize: 12,
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              borderRadius: 4,
            }
          : undefined
      }
    >
      {SUPPORTED_LANGUAGE_CODES.map((code) => (
        <option key={code} value={code}>
          {LANGUAGE_META[code].labelNative}
        </option>
      ))}
    </select>
  );
}
