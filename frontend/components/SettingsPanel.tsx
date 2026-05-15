"use client";

import { useState } from "react";

import { getSystemStatus } from "@/lib/api";
import * as logBus from "@/lib/log-bus";

import { CustomProvidersSection } from "./CustomProvidersSection";
import { ProvidersSection } from "./ProvidersSection";
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
  const [portTests, setPortTests] = useState<Record<string, TestResult>>({});
  const [copied, setCopied] = useState<string | null>(null);

  const setPortTest = (key: string, result: TestResult) =>
    setPortTests((prev) => ({ ...prev, [key]: result }));

  const runHttpTest = async (
    key: string,
    url: string,
    label: string,
  ): Promise<void> => {
    setPortTest(key, { kind: "pending" });
    try {
      const res = await fetch(url, { cache: "no-store" });
      const ok = res.ok;
      setPortTest(key, {
        kind: ok ? "success" : "error",
        detail: `HTTP ${res.status}`,
      });
      logBus.emit({
        source: "frontend",
        level: ok ? "success" : "warning",
        message: `port test ${label} → ${res.status}`,
        meta: { url, status: res.status },
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setPortTest(key, { kind: "error", detail: msg });
      logBus.emit({
        source: "frontend",
        level: "error",
        message: `port test ${label} failed`,
        meta: { url, error: msg },
      });
    }
  };

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

  const composeCmd = `BACKEND_PORT=${settings.backendHostPort} FRONTEND_PORT=${settings.frontendHostPort} POSTGRES_PORT=${settings.postgresHostPort} REDIS_PORT=${settings.redisHostPort} NEXT_PUBLIC_API_BASE_URL=http://localhost:${settings.backendHostPort} docker compose -f docker/compose.dev.yml up -d postgres redis backend frontend orchestrator`;

  const copy = (key: string, text: string) => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      void navigator.clipboard.writeText(text).then(() => {
        setCopied(key);
        setTimeout(() => setCopied(null), 1500);
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
          {settings.apiBaseUrlIsCustom
            ? "Custom override applied. Editing Backend port below won't change this — clear or reset to re-link."
            : "Auto-linked to Backend host port. Edit manually to override."}
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
        <p className={styles.help}>Display only — doesn&apos;t move the running frontend.</p>
      </Field>

      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>Docker Compose host ports</legend>
        <p className={styles.help}>
          Editing these values does <strong>not</strong> reconfigure the
          running Docker stack — they&apos;re local operator settings used to
          derive URLs and generate the compose-up command below. Restart the
          stack with those env vars to apply.
        </p>
        <PortRow
          label="Backend"
          containerPort={8000}
          hostPort={settings.backendHostPort}
          onChange={(p) => update({ backendHostPort: p })}
          url={`http://localhost:${settings.backendHostPort}`}
          testKey="backend"
          test={portTests.backend}
          onTest={() =>
            runHttpTest(
              "backend",
              `http://localhost:${settings.backendHostPort}/healthz`,
              "backend /healthz",
            )
          }
        />
        <PortRow
          label="Frontend"
          containerPort={3000}
          hostPort={settings.frontendHostPort}
          onChange={(p) => update({ frontendHostPort: p })}
          url={`http://localhost:${settings.frontendHostPort}`}
          testKey="frontend"
          test={portTests.frontend}
          onTest={() =>
            runHttpTest(
              "frontend",
              `http://localhost:${settings.frontendHostPort}/`,
              "frontend /",
            )
          }
        />
        <PortRow
          label="Postgres"
          containerPort={5432}
          hostPort={settings.postgresHostPort}
          onChange={(p) => update({ postgresHostPort: p })}
          url={null}
          testKey="postgres"
          test={portTests.postgres}
          onTest={null}
          note="Checked indirectly via backend /api/v1/system/status (database_reachable)."
        />
        <PortRow
          label="Redis"
          containerPort={6379}
          hostPort={settings.redisHostPort}
          onChange={(p) => update({ redisHostPort: p })}
          url={null}
          testKey="redis"
          test={portTests.redis}
          onTest={null}
          note="Raw TCP — browser cannot test directly. Visible via backend logs."
        />
        <PortRow
          label="MinIO"
          containerPort={9000}
          hostPort={settings.minioHostPort}
          onChange={(p) => update({ minioHostPort: p })}
          url={`http://localhost:${settings.minioHostPort}`}
          testKey="minio"
          test={portTests.minio}
          onTest={() =>
            runHttpTest(
              "minio",
              `http://localhost:${settings.minioHostPort}/minio/health/live`,
              "minio /minio/health/live",
            )
          }
        />

        <div className={styles.row}>
          <button
            type="button"
            className={styles.btn}
            onClick={() =>
              runHttpTest(
                "api-jobs",
                `${settings.apiBaseUrl}/api/v1/jobs`,
                "/api/v1/jobs",
              )
            }
          >
            Test /api/v1/jobs
          </button>
          {portTests["api-jobs"] &&
            (portTests["api-jobs"].kind === "success" ||
              portTests["api-jobs"].kind === "error") && (
              <span
                className={
                  portTests["api-jobs"].kind === "success"
                    ? styles.statusOk
                    : styles.statusErr
                }
              >
                {portTests["api-jobs"].detail}
              </span>
            )}
          <button
            type="button"
            className={styles.btn}
            onClick={() =>
              runHttpTest(
                "api-stages",
                `${settings.apiBaseUrl}/api/v1/stages`,
                "/api/v1/stages",
              )
            }
          >
            Test /api/v1/stages
          </button>
          {portTests["api-stages"] &&
            (portTests["api-stages"].kind === "success" ||
              portTests["api-stages"].kind === "error") && (
              <span
                className={
                  portTests["api-stages"].kind === "success"
                    ? styles.statusOk
                    : styles.statusErr
                }
              >
                {portTests["api-stages"].detail}
              </span>
            )}
        </div>
      </fieldset>

      <Field label="Compose-up command">
        <pre className={styles.cmdBox}>{composeCmd}</pre>
        <div className={styles.row}>
          <button
            type="button"
            className={styles.btn}
            onClick={() => copy("cmd", composeCmd)}
          >
            {copied === "cmd" ? "Copied" : "Copy command"}
          </button>
        </div>
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
        <p className={styles.help}>In-memory only; older entries dropped first.</p>
      </Field>

      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>Create-job defaults</legend>
        <Field label="Default target duration (s)">
          <input
            type="number"
            min={15}
            max={60}
            className={styles.input}
            value={settings.defaultTargetDurationSeconds}
            onChange={(e) =>
              update({
                defaultTargetDurationSeconds: clamp(Number(e.target.value), 15, 60),
              })
            }
          />
        </Field>
        <Field label="Default voice mode">
          <select
            className={styles.input}
            value={settings.defaultVoiceMode}
            onChange={(e) =>
              update({
                defaultVoiceMode:
                  e.target.value === "provided_audio" ? "provided_audio" : "tts",
              })
            }
          >
            <option value="tts">TTS from script</option>
            <option value="provided_audio">Provided audio</option>
          </select>
        </Field>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={settings.defaultFaceModeEnabled}
            onChange={(e) => update({ defaultFaceModeEnabled: e.target.checked })}
          />
          <span>Attach provided image by default</span>
        </label>
      </fieldset>

      <CustomProvidersSection />

      <ProvidersSection
        defaults={{
          llm: settings.defaultLlmProvider,
          tts: settings.defaultTtsProvider,
          video: settings.defaultVideoProvider,
        }}
        onDefaultsChange={(patch) => {
          const next: Record<string, string | null> = {};
          if (patch.llm !== undefined) next.defaultLlmProvider = patch.llm;
          if (patch.tts !== undefined) next.defaultTtsProvider = patch.tts;
          if (patch.video !== undefined) next.defaultVideoProvider = patch.video;
          update(next);
        }}
      />

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.btnGhost}
          onClick={() => {
            reset();
            setTestResult({ kind: "idle" });
            setPortTests({});
          }}
        >
          Reset to defaults
        </button>
      </div>

      <p className={styles.note}>
        Logs are local browser diagnostics. Editing Docker ports here does
        not restart Docker — copy the command above and run it from the host.
      </p>
    </div>
  );
}

interface PortRowProps {
  readonly label: string;
  readonly containerPort: number;
  readonly hostPort: number;
  readonly onChange: (n: number) => void;
  readonly url: string | null;
  readonly testKey: string;
  readonly test: TestResult | undefined;
  readonly onTest: (() => void) | null;
  readonly note?: string;
}

function PortRow({
  label,
  containerPort,
  hostPort,
  onChange,
  url,
  testKey,
  test,
  onTest,
  note,
}: PortRowProps) {
  return (
    <div className={styles.portRow}>
      <span className={styles.portLabel}>{label}</span>
      <span className={styles.portMap}>
        host{" "}
        <input
          className={styles.portInput}
          type="number"
          min={1}
          max={65535}
          value={hostPort}
          onChange={(e) =>
            onChange(clamp(Number(e.target.value), 1, 65535))
          }
          aria-label={`${label} host port`}
        />{" "}
        → container <code>{containerPort}</code>
      </span>
      {url && (
        <a className={styles.portUrl} href={url} target="_blank" rel="noreferrer">
          {url}
        </a>
      )}
      {onTest ? (
        <button
          type="button"
          className={styles.btnSmall}
          onClick={onTest}
          disabled={test?.kind === "pending"}
        >
          {test?.kind === "pending" ? "…" : "Test"}
        </button>
      ) : null}
      {test?.kind === "success" && (
        <span
          className={styles.statusOk}
          title={test.detail}
          data-testkey={testKey}
        >
          ✓ {test.detail}
        </span>
      )}
      {test?.kind === "error" && (
        <span className={styles.statusErr} title={test.detail}>
          ✗ {test.detail}
        </span>
      )}
      {note && !test && <span className={styles.help}>{note}</span>}
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

