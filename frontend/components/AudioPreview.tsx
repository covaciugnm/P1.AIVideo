"use client";

import { artifactContentUrl } from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageContext";

import styles from "./AudioPreview.module.css";

interface AudioPreviewProps {
  /** Source — either an uploaded artifact id, or a transient ObjectURL. */
  readonly src: { kind: "artifact"; artifactId: string } | { kind: "object"; url: string };
  readonly label?: string;
}

export function AudioPreview({ src, label }: AudioPreviewProps) {
  const t = useT();
  const url =
    src.kind === "artifact" ? artifactContentUrl(src.artifactId) : src.url;
  const displayLabel = label ?? t("common.preview");
  return (
    <div className={styles.wrapper}>
      <span className={styles.label}>{displayLabel}</span>
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio controls preload="none" src={url} className={styles.audio} />
    </div>
  );
}
