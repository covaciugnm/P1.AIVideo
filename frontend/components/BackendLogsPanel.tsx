"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { getBackendLogs, type BackendLogEntry } from "@/lib/api";
import { getActiveApiBaseUrl } from "@/lib/settings";
import { useT } from "@/lib/i18n/LanguageContext";
import * as logBus from "@/lib/log-bus";

import { useSettings } from "./SettingsContext";
import styles from "./BackendLogsPanel.module.css";

const POLL_INTERVAL_MS = 2000;
const MAX_BUFFER = 1000;
// Phase 20 — cap each fetch at 4s. Without a cap, an unreachable URL
// (stale tunnel hostname in localStorage, DNS that doesn't resolve,
// VPN dropped) would let the request hang indefinitely and the panel
// would sit empty with no error — the root cause of the "panoul e gol"
// bug reported in Phase 20. With a cap, we time out, surface the
// error in the diagnostic bar, and the next tick retries.
const FETCH_TIMEOUT_MS = 4000;

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
  // Phase 20 — subscribe to SettingsContext so the polling effect
  // re-mounts when the auto-detect picks a new working URL. Without
  // this, the panel would stick with whatever URL was current when
  // it first mounted, even after auto-detect switched to a reachable
  // one.
  const { settings } = useSettings();
  const apiBaseUrl = settings.apiBaseUrl;
  const [entries, setEntries] = useState<BackendLogEntry[]>([]);
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pollCount, setPollCount] = useState(0);
  const [okCount, setOkCount] = useState(0);
  const [lastFetchAt, setLastFetchAt] = useState<string | null>(null);
  const [lastDurationMs, setLastDurationMs] = useState<number | null>(null);
  const [activeUrl, setActiveUrl] = useState<string>("");
  const lastSeqRef = useRef<number | undefined>(undefined);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  // Phase 20 — Reload button forces a from-scratch refetch. We bump
  // this counter; the effect lists it as a dep so it re-runs.
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    if (paused) return;
    let cancelled = false;
    const inflight = new Set<AbortController>();
    const tick = async () => {
      const urlNow = getActiveApiBaseUrl();
      setActiveUrl(urlNow);
      const ctrl = new AbortController();
      inflight.add(ctrl);
      const timeoutId = window.setTimeout(
        () => ctrl.abort(),
        FETCH_TIMEOUT_MS,
      );
      const startedAt = performance.now();
      try {
        const resp = await getBackendLogs(
          {
            since_seq: lastSeqRef.current,
            limit: 200,
          },
          ctrl.signal,
        );
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
        setLastDurationMs(Math.round(performance.now() - startedAt));
        setPollCount((n) => n + 1);
        setOkCount((n) => n + 1);
      } catch (e) {
        if (cancelled) return;
        const isAbort = e instanceof DOMException && e.name === "AbortError";
        const msg = isAbort
          ? `fetch timed out after ${FETCH_TIMEOUT_MS}ms (URL: ${urlNow || "—"})`
          : e instanceof Error
            ? e.message
            : String(e);
        setError(msg);
        setLastFetchAt(new Date().toISOString());
        setLastDurationMs(Math.round(performance.now() - startedAt));
        setPollCount((n) => n + 1);
        // Bubble into the frontend Logs tab so the operator can
        // correlate even without staring at this panel.
        logBus.emit({
          source: "api",
          level: "warning",
          message: `backend-logs poll failed: ${msg}`,
          meta: { url: urlNow, since_seq: lastSeqRef.current },
        });
      } finally {
        window.clearTimeout(timeoutId);
        inflight.delete(ctrl);
      }
    };
    tick();
    const id = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      for (const c of inflight) c.abort();
    };
    // Re-run on URL change (apiBaseUrl) and on manual reload.
  }, [paused, apiBaseUrl, reloadNonce]);

  // Phase 20 — manual Reload: clear buffer, forget last seq, bump nonce
  // to restart the effect. Useful when the operator just changed the
  // API URL in Settings and wants an immediate from-scratch fetch.
  const handleReload = () => {
    setEntries([]);
    lastSeqRef.current = undefined;
    setError(null);
    setReloadNonce((n) => n + 1);
  };

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
        <span><strong>Polls:</strong> {pollCount}{okCount !== pollCount ? ` (${okCount} ok)` : ""}</span>
        <span><strong>Last:</strong> {lastFetchAt ? new Date(lastFetchAt).toLocaleTimeString() : "—"}{lastDurationMs !== null ? ` (${lastDurationMs}ms)` : ""}</span>
        <span><strong>Entries:</strong> {entries.length}</span>
        {error ? (
          <span className={styles.diagError}>⚠️ {error}</span>
        ) : pollCount === 0 ? (
          <span className={styles.diagOk}>… waiting</span>
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
          onClick={handleReload}
          title={t("backendLogs.reloadHelp")}
        >
          {t("backendLogs.reload")}
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
          <div className={styles.empty}>
            {filter
              ? t("backendLogs.emptyFiltered")
              : pollCount === 0
                ? t("backendLogs.emptyWaiting")
                : okCount === 0 && error
                  ? t("backendLogs.emptyError")
                  : t("backendLogs.empty")}
          </div>
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
