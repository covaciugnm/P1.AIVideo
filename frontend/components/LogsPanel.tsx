"use client";

import { useMemo, useState } from "react";

import { getActiveApiBaseUrl } from "@/lib/api";
import * as logBus from "@/lib/log-bus";
import type { LogEntry, LogLevel, LogSource } from "@/lib/log-bus";

import { useLogs } from "./LogsContext";
import { useSettings } from "./SettingsContext";
import styles from "./LogsPanel.module.css";

const LEVELS: readonly LogLevel[] = ["info", "success", "warning", "error"];

// Phase 8E — fields safe to export from the settings snapshot.
// Anything not in this list (e.g. a future API token / cookie) is
// dropped before the JSON ever hits the operator's download.
const _EXPORTABLE_SETTINGS_KEYS = [
  "apiBaseUrl",
  "apiBaseUrlIsCustom",
  "backendHostPort",
  "autoPollingEnabled",
  "pollingIntervalSeconds",
  "showFrontendLogs",
  "showBackendLogs",
  "showApiLogs",
  "showSystemLogs",
  "defaultScriptProvider",
  "defaultTtsProvider",
  "defaultVideoProvider",
] as const;

export function LogsPanel() {
  const { entries, clear } = useLogs();
  const { settings } = useSettings();
  const [levelFilter, setLevelFilter] = useState<LogLevel | "all">("all");

  const visible = useMemo(() => {
    return entries.filter((e) => sourceAllowed(e.source, settings))
      .filter((e) => levelFilter === "all" || e.level === levelFilter);
  }, [entries, settings, levelFilter]);

  const handleExportJson = () => downloadLogs(visible, settings, "json");
  const handleExportTxt = () => downloadLogs(visible, settings, "txt");

  return (
    <div className={styles.panel}>
      <div className={styles.toolbar}>
        <select
          className={styles.select}
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value as LogLevel | "all")}
          aria-label="Filter by level"
        >
          <option value="all">All levels</option>
          {LEVELS.map((level) => (
            <option key={level} value={level}>
              {level}
            </option>
          ))}
        </select>
        <span className={styles.count}>{visible.length} / {entries.length}</span>
        <button
          type="button"
          className={styles.exportBtn}
          onClick={handleExportJson}
          disabled={entries.length === 0}
          title="Download visible logs as JSON"
        >
          ↓ JSON
        </button>
        <button
          type="button"
          className={styles.exportBtn}
          onClick={handleExportTxt}
          disabled={entries.length === 0}
          title="Download visible logs as plain text"
        >
          ↓ TXT
        </button>
        <button type="button" className={styles.clear} onClick={clear}>
          Clear
        </button>
      </div>
      <ul className={styles.list}>
        {visible.length === 0 && (
          <li className={styles.empty}>
            {entries.length === 0
              ? "No log entries yet."
              : "No entries match the current filters."}
          </li>
        )}
        {visible.map((entry) => (
          <LogEntryItem key={entry.id} entry={entry} />
        ))}
      </ul>
    </div>
  );
}

function sourceAllowed(source: LogSource, settings: ReturnType<typeof useSettings>["settings"]): boolean {
  switch (source) {
    case "frontend":
      return settings.showFrontendLogs;
    case "backend":
      return settings.showBackendLogs;
    case "api":
      return settings.showApiLogs;
    case "system":
      return settings.showSystemLogs;
    default:
      return true;
  }
}

function LogEntryItem({ entry }: { readonly entry: LogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const hasMeta = entry.meta && Object.keys(entry.meta).length > 0;
  const time = formatTime(entry.timestamp);
  return (
    <li className={`${styles.entry} ${styles[`level-${entry.level}`]}`}>
      <div className={styles.row}>
        <span className={styles.time}>{time}</span>
        <span className={`${styles.tag} ${styles[`tag-${entry.source}`]}`}>{entry.source}</span>
        <span className={`${styles.level} ${styles[`level-tag-${entry.level}`]}`}>{entry.level}</span>
        {hasMeta && (
          <button
            type="button"
            className={styles.expand}
            onClick={() => setExpanded((e) => !e)}
            aria-label={expanded ? "Hide details" : "Show details"}
          >
            {expanded ? "−" : "+"}
          </button>
        )}
      </div>
      <div className={styles.message}>{entry.message}</div>
      {expanded && hasMeta && (
        <pre className={styles.meta}>{JSON.stringify(entry.meta, null, 2)}</pre>
      )}
    </li>
  );
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}


// ---------------------------------------------------------------------------
// Phase 8E — log export helpers
// ---------------------------------------------------------------------------


type SettingsLike = ReturnType<typeof useSettings>["settings"];


function safeSettingsSnapshot(settings: SettingsLike): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of _EXPORTABLE_SETTINGS_KEYS) {
    const v = (settings as unknown as Record<string, unknown>)[key];
    if (v !== undefined) out[key] = v;
  }
  return out;
}


function buildJsonExport(
  entries: readonly LogEntry[],
  settings: SettingsLike,
): string {
  const payload = {
    exported_at: new Date().toISOString(),
    app: "P1.AIVideo frontend",
    active_api_base_url: getActiveApiBaseUrl(),
    frontend_url: typeof window !== "undefined" ? window.location.href : null,
    settings_snapshot: safeSettingsSnapshot(settings),
    entries: entries.map((e) => ({
      id: e.id,
      timestamp: e.timestamp,
      source: e.source,
      level: e.level,
      message: e.message,
      meta: e.meta ?? null,
    })),
  };
  return JSON.stringify(payload, null, 2);
}


function buildTxtExport(entries: readonly LogEntry[]): string {
  const lines: string[] = [];
  for (const e of entries) {
    const meta = e.meta && Object.keys(e.meta).length > 0
      ? ` ${JSON.stringify(e.meta)}`
      : "";
    lines.push(
      `${e.timestamp} | ${e.level.padEnd(7)} | ${e.source.padEnd(8)} | ${e.message}${meta}`,
    );
  }
  return lines.join("\n") + "\n";
}


function downloadLogs(
  visible: readonly LogEntry[],
  settings: SettingsLike,
  format: "json" | "txt",
): void {
  if (typeof window === "undefined") return;
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const filename = `aivideo-logs-${stamp}.${format}`;
  const mime = format === "json" ? "application/json" : "text/plain";
  const body =
    format === "json"
      ? buildJsonExport(visible, settings)
      : buildTxtExport(visible);
  const blob = new Blob([body], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  logBus.emit({
    source: "frontend",
    level: "info",
    message: `Exported ${visible.length} log entries as ${format.toUpperCase()}`,
    meta: { filename, count: visible.length, format },
  });
}
