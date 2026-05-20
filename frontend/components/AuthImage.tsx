"use client";

// Renders an image from a token-protected endpoint. A plain <img src> can't
// send the Authorization header, so we fetch the bytes with the bearer token,
// turn them into an object URL, and render that. Clicking opens the same
// object URL in a new tab.
import { useEffect, useState, type CSSProperties } from "react";

import { authHeaders, handleUnauthorized } from "@/lib/auth";

export function AuthImage({
  src,
  alt,
  style,
  className,
}: {
  readonly src: string;
  readonly alt: string;
  readonly style?: CSSProperties;
  readonly className?: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let revoked = false;
    let obj: string | null = null;
    (async () => {
      try {
        const res = await fetch(src, { headers: authHeaders(), cache: "no-store" });
        if (res.status === 401) { handleUnauthorized(); return; }
        if (!res.ok) { setFailed(true); return; }
        obj = URL.createObjectURL(await res.blob());
        if (!revoked) setUrl(obj);
      } catch {
        setFailed(true);
      }
    })();
    return () => { revoked = true; if (obj) URL.revokeObjectURL(obj); };
  }, [src]);

  if (failed) {
    return (
      <div className={className} style={{ ...style, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--surface-2)", color: "var(--text-muted)", fontSize: 12, minHeight: 120 }}>
        imagine indisponibilă
      </div>
    );
  }
  if (!url) {
    return <div className={className} style={{ ...style, background: "var(--surface-2)", minHeight: 120 }} />;
  }
  return (
    <a href={url} target="_blank" rel="noreferrer" style={{ display: "block", cursor: "zoom-in" }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={url} alt={alt} className={className} style={style} />
    </a>
  );
}
