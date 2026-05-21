"use client";

// Services catalog — a table-of-contents of every service TYPE and, under
// each, every provider with its readiness (🟢 functional / 🔴 implementable
// but not functional yet) + a one-word stage (running/config/install/...).
import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import type { ProviderInfo, ProvidersResponse } from "@/lib/types";

import styles from "./ServicesPanel.module.css";

// Statuses that mean the service actually works right now.
const FUNCTIONAL = new Set(["configured", "available", "ready", "ok"]);

// Map a catalog status → short stage word shown before the description.
function stageOf(status: string): string {
  switch (status) {
    case "configured": return "config ✓";
    case "available":
    case "ready": return "running";
    case "not_configured": return "config";
    case "runtime_missing": return "install";
    case "assets_missing": return "download";
    case "gpu_unavailable": return "gpu";
    case "not_implemented": return "de implementat";
    default: return status;
  }
}

const CATEGORIES: readonly { key: keyof ProvidersResponse; title: string }[] = [
  { key: "llm", title: "Modele LLM" },
  { key: "tts", title: "Voci TTS" },
  { key: "image_generator", title: "Generare imagini" },
  { key: "video_generator", title: "Generare video / Lip-sync" },
  { key: "audio_processor", title: "Procesare audio" },
  { key: "image_processor", title: "Procesare imagini" },
];

const MODE_LABELS: Record<string, string> = {
  off: "Oprit", mixed: "Mixt", permanent: "Permanent",
};

function DockerServices() {
  const [services, setServices] = useState<api.DockerService[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const reload = async () => {
    try { setServices((await api.getSystemServices()).services); } catch { /* ignore */ }
  };
  useEffect(() => {
    void reload();
    const id = window.setInterval(reload, 8000); // live running state
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const change = async (svc: string, mode: string) => {
    setBusy(svc);
    try { await api.setServiceMode(svc, mode, true); await reload(); }
    finally { setBusy(null); }
  };

  if (!services) return null;
  return (
    <section className={styles.group}>
      <h4 className={styles.groupTitle}>Servicii Docker (GPU)</h4>
      <p className={styles.intro}>
        Oprit = niciodată · Mixt = pornit la cerere, oprit la 10s după sarcină · Permanent = mereu pornit.
      </p>
      <ul className={styles.list}>
        {services.map((s) => (
          <li key={s.service} className={styles.row} style={{ gridTemplateColumns: "14px 1fr auto" }}>
            <span className={s.running ? styles.dotGreen : styles.dotRed} aria-hidden />
            <span className={styles.name}>{s.service.replace("model-", "")}</span>
            <span style={{ display: "inline-flex", gap: 4 }}>
              {(["off", "mixed", "permanent"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  className="btn"
                  disabled={busy === s.service}
                  onClick={() => change(s.service, m)}
                  style={{
                    fontSize: 11, padding: "3px 7px",
                    background: s.mode === m ? "var(--accent-strong)" : "var(--surface-2)",
                    color: s.mode === m ? "#fff" : "var(--text-muted)",
                    border: "1px solid var(--border)",
                  }}
                >
                  {MODE_LABELS[m]}
                </button>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ServicesPanel() {
  const [data, setData] = useState<ProvidersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    void (async () => {
      try { setData(await api.getProviders(ctrl.signal)); }
      catch (e) { setError((e as Error).message); }
    })();
    return () => ctrl.abort();
  }, []);

  if (error) return <p className={styles.error}>{error}</p>;
  if (!data) return <p className={styles.muted}>Se încarcă serviciile…</p>;

  const row = (p: ProviderInfo) => {
    const ok = FUNCTIONAL.has(p.status);
    return (
      <li key={p.provider_id} className={styles.row} title={p.notes || undefined}>
        <span className={ok ? styles.dotGreen : styles.dotRed} aria-hidden />
        <span className={styles.stage}>{stageOf(p.status)}</span>
        <span className={styles.name}>{p.label}</span>
      </li>
    );
  };

  return (
    <div className={styles.wrap}>
      <p className={styles.intro}>
        Toate serviciile (open-source sau API). 🟢 funcțional · 🔴 de implementat.
      </p>
      <DockerServices />
      {CATEGORIES.map(({ key, title }) => {
        const list = (data[key] ?? []) as readonly ProviderInfo[];
        if (list.length === 0) return null;
        const okCount = list.filter((p) => FUNCTIONAL.has(p.status)).length;
        return (
          <section key={String(key)} className={styles.group}>
            <h4 className={styles.groupTitle}>
              {title} <span className={styles.count}>({okCount}/{list.length})</span>
            </h4>
            <ul className={styles.list}>{list.map(row)}</ul>
          </section>
        );
      })}
    </div>
  );
}
