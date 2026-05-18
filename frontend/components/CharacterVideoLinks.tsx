"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import {
  getCharacterVideos,
  type CharacterVideoLinkItem,
} from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageContext";

interface Props {
  readonly characterId: string;
}

function fmtDate(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function fmtDur(s: number | null): string {
  if (s === null || s === undefined) return "—";
  return `${s.toFixed(1)}s`;
}

export function CharacterVideoLinks({ characterId }: Props) {
  const t = useT();
  const [items, setItems] = useState<CharacterVideoLinkItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setItems(null);
    setError(null);
    getCharacterVideos(characterId, ctrl.signal)
      .then((r) => setItems(r.items))
      .catch((e) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => ctrl.abort();
  }, [characterId]);

  if (error) return <div className="card">⚠️ {error}</div>;
  if (items === null) return <div className="card muted">{t("common.loading")}…</div>;
  if (items.length === 0) {
    return (
      <div className="card muted">
        {t("characterVideos.empty")}
      </div>
    );
  }

  return (
    <div className="card">
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.95em" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border)" }}>
            <th style={{ padding: "8px 6px" }}>{t("characterVideos.colCreated")}</th>
            <th style={{ padding: "8px 6px" }}>{t("characterVideos.colProvider")}</th>
            <th style={{ padding: "8px 6px" }}>{t("characterVideos.colDuration")}</th>
            <th style={{ padding: "8px 6px" }}>{t("characterVideos.colJobStatus")}</th>
            <th style={{ padding: "8px 6px" }}>{t("characterVideos.colJobLink")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((v) => (
            <tr key={v.id} style={{ borderBottom: "1px solid var(--border)" }}>
              <td style={{ padding: "6px" }}>{fmtDate(v.created_at)}</td>
              <td style={{ padding: "6px", fontFamily: "monospace" }}>
                {v.provider_id ?? "—"}
              </td>
              <td style={{ padding: "6px" }}>{fmtDur(v.duration_seconds)}</td>
              <td style={{ padding: "6px" }}>
                <span style={{ fontFamily: "monospace" }}>{v.job_status ?? "—"}</span>
              </td>
              <td style={{ padding: "6px" }}>
                <Link
                  href={`/jobs/${v.job_id}`}
                  className="btn"
                  style={{ padding: "4px 10px", fontSize: "0.9em" }}
                >
                  → /jobs/{v.job_id.slice(0, 8)}…
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
