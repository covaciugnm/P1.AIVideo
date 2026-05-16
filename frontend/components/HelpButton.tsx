"use client";

import { useT } from "@/lib/i18n/LanguageContext";

import { useHelp } from "./HelpContext";
import styles from "./HelpButton.module.css";

export function HelpButton() {
  const help = useHelp();
  const t = useT();

  if (help.open) return null;

  const ariaLabel = `${t("help.open")} (?)`;

  return (
    <button
      type="button"
      className={styles.fab}
      onClick={() => help.openHelp()}
      aria-label={ariaLabel}
      title={ariaLabel}
    >
      <span aria-hidden className={styles.glyph}>
        ?
      </span>
      <span className={styles.label}>{t("nav.help")}</span>
      <kbd className={styles.kbd}>?</kbd>
    </button>
  );
}
