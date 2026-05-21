"use client";

import { useEffect, useState } from "react";

import { artifactContentUrl } from "@/lib/api";
import { authHeaders, handleUnauthorized } from "@/lib/auth";
import { useT } from "@/lib/i18n/LanguageContext";

import styles from "./AudioPreview.module.css";

interface AudioPreviewProps {
  /** Source — either an uploaded artifact id, or a transient ObjectURL. */
  readonly src: { kind: "artifact"; artifactId: string } | { kind: "object"; url: string };
  readonly label?: string;
}

export function AudioPreview({ src, label }: AudioPreviewProps) {
  const t = useT();
  const displayLabel = label ?? t("common.preview");
  // Object-URL sources play directly. Artifact sources are token-protected,
  // so a plain <audio src> would 401 — fetch the bytes with the bearer token
  // and play an object URL instead.
  const [objectUrl, setObjectUrl] = useState<string | null>(
    src.kind === "object" ? src.url : null,
  );
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (src.kind === "object") { setObjectUrl(src.url); return; }
    let revoked = false;
    let obj: string | null = null;
    setObjectUrl(null);
    setFailed(false);
    (async () => {
      try {
        const res = await fetch(artifactContentUrl(src.artifactId), {
          // allow-raw-fetch: needs raw audio bytes with the bearer header.
          headers: authHeaders(),
          cache: "no-store",
        });
        if (res.status === 401) { handleUnauthorized(); return; }
        if (!res.ok) { setFailed(true); return; }
        obj = URL.createObjectURL(await res.blob());
        if (!revoked) setObjectUrl(obj);
      } catch {
        setFailed(true);
      }
    })();
    return () => { revoked = true; if (obj) URL.revokeObjectURL(obj); };
  }, [src]);

  return (
    <div className={styles.wrapper}>
      <span className={styles.label}>{displayLabel}</span>
      {failed ? (
        <span style={{ color: "var(--danger)", fontSize: 12 }}>audio indisponibil</span>
      ) : objectUrl ? (
        // eslint-disable-next-line jsx-a11y/media-has-caption
        <audio controls preload="none" src={objectUrl} className={styles.audio} />
      ) : (
        <span className="muted" style={{ fontSize: 12 }}>se încarcă audio…</span>
      )}
    </div>
  );
}
