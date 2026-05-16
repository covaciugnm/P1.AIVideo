"use client";

import { useT } from "@/lib/i18n/LanguageContext";

import styles from "./LoadingState.module.css";

interface LoadingStateProps {
  readonly label?: string;
}

export function LoadingState({ label }: LoadingStateProps) {
  const t = useT();
  return (
    <div className={styles.wrapper} aria-busy="true">
      <span className={styles.spinner} aria-hidden="true" />
      <span className={styles.label}>{label ?? t("common.loading")}</span>
    </div>
  );
}
