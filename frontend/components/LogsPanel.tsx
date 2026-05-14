"use client";

import { useMemo, useState } from "react";

import type { LogEntry, LogLevel, LogSource } from "@/lib/log-bus";

import { useLogs } from "./LogsContext";
import { useSettings } from "./SettingsContext";
import styles from "./LogsPanel.module.css";

const LEVELS: readonly LogLevel[] = ["info", "success", "warning", "error"];

export function LogsPanel() {
  const { entries, clear } = useLogs();
  const { settings } = useSettings();
  const [levelFilter, setLevelFilter] = useState<LogLevel | "all">("all");

  const visible = useMemo(() => {
    return entries.filter((e) => sourceAllowed(e.source, settings))
      .filter((e) => levelFilter === "all" || e.level === levelFilter);
  }, [entries, settings, levelFilter]);

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
