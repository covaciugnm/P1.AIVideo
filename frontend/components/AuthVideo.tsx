"use client";

// Plays a token-protected artifact video inline. Like AuthImage: fetch the
// bytes with the bearer token, build an object URL, render <video controls>.
import { useEffect, useState, type CSSProperties } from "react";

import { authHeaders, handleUnauthorized } from "@/lib/auth";

export function AuthVideo({ src, style }: { readonly src: string; readonly style?: CSSProperties }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let revoked = false;
    let obj: string | null = null;
    (async () => {
      try {
        // allow-raw-fetch: needs raw video bytes with the bearer header.
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

  if (failed) return <p style={{ color: "var(--danger)", fontSize: 13 }}>video indisponibil</p>;
  if (!url) return <p className="muted" style={{ fontSize: 12 }}>se încarcă video…</p>;
  return (
    // eslint-disable-next-line jsx-a11y/media-has-caption
    <video controls src={url} style={{ width: "100%", borderRadius: 8, ...style }} />
  );
}
