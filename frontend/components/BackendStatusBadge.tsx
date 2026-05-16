"use client";

import { useEffect, useRef, useState } from "react";

import { getSystemStatus } from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageContext";
import * as logBus from "@/lib/log-bus";
import { formatRelative } from "@/lib/format";

import { useSettings } from "./SettingsContext";
import styles from "./BackendStatusBadge.module.css";

const CHECK_INTERVAL_MS = 15_000;

export function BackendStatusBadge() {
  const t = useT();
  const { settings, hydrated } = useSettings();
  const [reachable, setReachable] = useState<boolean | null>(null);
  const [lastOk, setLastOk] = useState<string | null>(null);
  const [lastErr, setLastErr] = useState<string | null>(null);
  const wasReachable = useRef<boolean | null>(null);

  useEffect(() => {
    if (!hydrated) return;
    const controller = new AbortController();
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        await getSystemStatus(controller.signal);
        if (cancelled) return;
        const wasOk = wasReachable.current;
        if (wasOk === false) {
          logBus.emit({
            source: "backend",
            level: "success",
            message: `backend reachable again at ${settings.apiBaseUrl}`,
          });
        } else if (wasOk === null) {
          logBus.emit({
            source: "backend",
            level: "info",
            message: `backend reachable at ${settings.apiBaseUrl}`,
          });
        }
        wasReachable.current = true;
        setReachable(true);
        setLastOk(new Date().toISOString());
        setLastErr(null);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        const wasOk = wasReachable.current;
        if (wasOk !== false) {
          logBus.emit({
            source: "backend",
            level: "error",
            message: `backend unreachable at ${settings.apiBaseUrl} — check Settings → Backend API Base URL`,
            meta: { error: err instanceof Error ? err.message : String(err) },
          });
        }
        wasReachable.current = false;
        setReachable(false);
        setLastErr(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) timer = setTimeout(tick, CHECK_INTERVAL_MS);
      }
    };

    // Reset state when the URL changes so the indicator re-evaluates from
    // scratch (otherwise a quick switch could keep a stale "ok" badge).
    wasReachable.current = null;
    setReachable(null);
    setLastOk(null);
    setLastErr(null);

    void tick();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer !== null) clearTimeout(timer);
    };
  }, [hydrated, settings.apiBaseUrl]);

  const dotClass =
    reachable === null
      ? styles.dotPending
      : reachable
        ? styles.dotOk
        : styles.dotErr;

  const label =
    reachable === null
      ? t("settings.testing")
      : reachable
        ? t("settings.testSuccess")
        : t("settings.testFailed");

  const title =
    reachable === false && lastErr
      ? `${settings.apiBaseUrl}\n${lastErr}`
      : `${settings.apiBaseUrl}${lastOk ? ` — last OK ${formatRelative(lastOk)}` : ""}`;

  return (
    <div className={styles.wrapper} title={title}>
      <span className={`${styles.dot} ${dotClass}`} aria-hidden="true" />
      <div className={styles.col}>
        <span className={styles.label}>{label}</span>
        <span className={styles.url}>{settings.apiBaseUrl}</span>
      </div>
      {reachable === false && (
        <span className={styles.hint}>{t("badges.openSettingsToChangeUrl")}</span>
      )}
    </div>
  );
}
