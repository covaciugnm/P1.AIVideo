"use client";

import { useState } from "react";

import { getSystemStatus } from "@/lib/api";
import * as logBus from "@/lib/log-bus";

import { useSettings } from "./SettingsContext";
import styles from "./SettingsPanel.module.css";

type TestResult =
  | { kind: "idle" }
  | { kind: "pending" }
  | { kind: "success"; detail: string }
  | { kind: "error"; detail: string };

export function SettingsPanel() {
  const { settings, update, reset } = useSettings();
  const [testResult, setTestResult] = useState<TestResult>({ kind: "idle" });

  const onTestConnection = async () => {
    setTestResult({ kind: "pending" });
    const controller = new AbortController();
    try {
      const status = await getSystemStatus(controller.signal);
      const summary = `${status.app_name} · ${status.phase} · db=${status.database_reachable ? "ok" : "FAIL"}`;
      setTestResult({ kind: "success", detail: summary });
      logBus.emit({
        source: "frontend",
        level: "success",
        message: `test connection passed: ${settings.apiBaseUrl}`,
        meta: { phase: status.phase, database_reachable: status.database_reachable },
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setTestResult({ kind: "error", detail: msg });
      logBus.emit({
        source: "frontend",
        level: "error",
        message: `test connection failed: ${settings.apiBaseUrl}`,
        meta: { error: msg },
      });
    }
  };

  return (
    <div className={styles.panel}>
      <Field label="Backend API Base URL">
        <input
          type="url"
          className={styles.input}
          value={settings.apiBaseUrl}
          onChange={(e) => update({ apiBaseUrl: e.target.value })}
          placeholder="http://localhost:8000"
        />
        <p className={styles.help}>
          Default is baked from <code>NEXT_PUBLIC_API_BASE_URL</code>; this
          override is applied at runtime and persisted to localStorage.
        </p>
        <div className={styles.row}>
          <button
            type="button"
            className={styles.btn}
            onClick={onTestConnection}
            disabled={testResult.kind === "pending"}
          >
            {testResult.kind === "pending" ? "Testing…" : "Test backend connection"}
          </button>
          {testResult.kind === "success" && (
            <span className={`${styles.status} ${styles.statusOk}`}>{testResult.detail}</span>
          )}
          {testResult.kind === "error" && (
            <span className={`${styles.status} ${styles.statusErr}`}>{testResult.detail}</span>
          )}
        </div>
      </Field>

      <Field label="Frontend URL">
        <input
          type="url"
          className={styles.input}
          value={settings.frontendUrl}
          onChange={(e) => update({ frontendUrl: e.target.value })}
          placeholder="http://localhost:3000"
        />
        <p className={styles.help}>
          Used for display only; doesn&apos;t affect runtime routing.
        </p>
      </Field>

      <Field label="Polling interval (seconds)">
        <input
          type="number"
          min={1}
          max={600}
          className={styles.input}
          value={settings.pollingIntervalSeconds}
          onChange={(e) =>
            update({
              pollingIntervalSeconds: clamp(Number(e.target.value), 1, 600),
            })
          }
        />
      </Field>

      <Field label="">
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={settings.autoPollingEnabled}
            onChange={(e) => update({ autoPollingEnabled: e.target.checked })}
          />
          <span>Enable auto polling</span>
        </label>
      </Field>

      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>Log sources</legend>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={settings.showFrontendLogs}
            onChange={(e) => update({ showFrontendLogs: e.target.checked })}
          />
          <span>Frontend</span>
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={settings.showBackendLogs}
            onChange={(e) => update({ showBackendLogs: e.target.checked })}
          />
          <span>Backend</span>
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={settings.showApiLogs}
            onChange={(e) => update({ showApiLogs: e.target.checked })}
          />
          <span>API</span>
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={settings.showSystemLogs}
            onChange={(e) => update({ showSystemLogs: e.target.checked })}
          />
          <span>System</span>
        </label>
      </fieldset>

      <Field label="Max log entries">
        <input
          type="number"
          min={50}
          max={5000}
          step={50}
          className={styles.input}
          value={settings.maxLogEntries}
          onChange={(e) =>
            update({ maxLogEntries: clamp(Number(e.target.value), 50, 5000) })
          }
        />
        <p className={styles.help}>
          Older entries are dropped once the buffer is full. In-memory only.
        </p>
      </Field>

      <div className={styles.actions}>
        <button type="button" className={styles.btnGhost} onClick={reset}>
          Reset to defaults
        </button>
      </div>

      <p className={styles.note}>
        Logs are local browser diagnostics. They are not stored on the
        backend and disappear when you close the tab.
      </p>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  readonly label: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div className={styles.field}>
      {label && <label className={styles.label}>{label}</label>}
      {children}
    </div>
  );
}

function clamp(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) return min;
  return Math.max(min, Math.min(max, value));
}
