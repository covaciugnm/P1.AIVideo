"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { getBackendLogs, type BackendLogEntry } from "@/lib/api";
import { getActiveApiBaseUrl } from "@/lib/settings";
import { useT } from "@/lib/i18n/LanguageContext";

import styles from "./BackendLogsPanel.module.css";

const POLL_INTERVAL_MS = 2000;
const MAX_BUFFER = 1000;

function fmtTime(ts: number): string {
  const d = new Date(ts * 1000);
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  const s = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${h}:${m}:${s}.${ms}`;
}

function levelClass(level: string): string {
  const lvl = level.toUpperCase();
  if (lvl === "ERROR" || lvl === "CRITICAL") return styles.levelError;
  if (lvl === "WARNING" || lvl === "WARN") return styles.levelWarn;
  if (lvl === "INFO") return styles.levelInfo;
  return styles.levelDebug;
}

export function BackendLogsPanel() {
  const t = useT();
  const [entries, setEntries] = useState<BackendLogEntry[]>([]);
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pollCount, setPollCount] = useState(0);
  const [lastFetchAt, setLastFetchAt] = useState<string | null>(null);
  const [activeUrl, setActiveUrl] = useState<string>("");
  const lastSeqRef = useRef<number | undefined>(undefined);
  const bodyRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (paused) return;
    let cancelled = false;
    const tick = async () => {
      setActiveUrl(getActiveApiBaseUrl());
      try {
        const resp = await getBackendLogs({
          since_seq: lastSeqRef.current,
          limit: 200,
        });
        if (cancelled) return;
        if (resp.entries.length > 0) {
          lastSeqRef.current = Math.max(
            lastSeqRef.current ?? 0,
            ...resp.entries.map((e) => e.seq),
          );
          setEntries((prev) => {
            const next = [...prev, ...resp.entries];
            return next.length > MAX_BUFFER ? next.slice(-MAX_BUFFER) : next;
          });
        } else {
          lastSeqRef.current = resp.latest_seq;
        }
        setError(null);
        setLastFetchAt(new Date().toISOString());
        setPollCount((n) => n + 1);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setLastFetchAt(new Date().toISOString());
          setPollCount((n) => n + 1);
        }
      }
    };
    tick();
    const id = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [paused]);

  const filtered = useMemo(() => {
    if (!filter) return entries;
    const needle = filter.toLowerCase();
    return entries.filter(
      (e) =>
        e.message.toLowerCase().includes(needle)
        || e.logger.toLowerCase().includes(needle)
        || e.level.toLowerCase().includes(needle),
    );
  }, [entries, filter]);

  useEffect(() => {
    // Phase 15H — sticky scroll: ONLY auto-scroll to bottom if the user
    // is already at the bottom (≤80px from end). If they've scrolled up
    // to read history, do NOT yank them back down each tick.
    if (paused || !bodyRef.current) return;
    const el = bodyRef.current;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distFromBottom < 80) {
      el.scrollTop = el.scrollHeight;
    }
  }, [filtered, paused]);

  return (
    <div className={styles.panel}>
      <div className={styles.diagBar}>
        <span><strong>API:</strong> <code>{activeUrl || "—"}</code></span>
        <span><strong>Polls:</strong> {pollCount}</span>
        <span><strong>Last:</strong> {lastFetchAt ? new Date(lastFetchAt).toLocaleTimeString() : "—"}</span>
        <span><strong>Entries:</strong> {entries.length}</span>
        {error ? (
          <span className={styles.diagError}>⚠️ {error}</span>
        ) : (
          <span className={styles.diagOk}>✓ OK</span>
        )}
      </div>
      <div className={styles.toolbar}>
        <input
          type="search"
          className={styles.filter}
          placeholder={t("backendLogs.filterPlaceholder")}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <button
          type="button"
          className={styles.button}
          onClick={() => setPaused((p) => !p)}
        >
          {paused ? t("backendLogs.resume") : t("backendLogs.pause")}
        </button>
        <button
          type="button"
          className={styles.button}
          onClick={() => {
            setEntries([]);
            lastSeqRef.current = undefined;
          }}
        >
          {t("backendLogs.clear")}
        </button>
        <span className={styles.count}>
          {t("backendLogs.count").replace("{n}", String(entries.length))}
        </span>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      <div className={styles.body} ref={bodyRef}>
        {filtered.length === 0 && (
          <div className={styles.empty}>{t("backendLogs.empty")}</div>
        )}
        {filtered.map((e) => {
          // Defensive: backend may emit empty messages from libraries that
          // log just structured args. Surface the logger name + level so
          // the row never renders blank.
          const visibleMessage = (e.message ?? "").trim() || "(no message)";
          return (
            <div key={e.seq} className={styles.entry}>
              <span className={styles.ts}>{fmtTime(e.ts)}</span>
              <span className={`${styles.level} ${levelClass(e.level)}`}>{e.level}</span>
              <span className={styles.logger} title={e.logger}>{e.logger}</span>
              <span className={styles.message}>{visibleMessage}</span>
              {Object.keys(e.extra).length > 0 && (
                <span className={styles.extra}>{JSON.stringify(e.extra)}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
