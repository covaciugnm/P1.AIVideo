"use client";

import { useEffect, useState } from "react";

import { getSystemStatus } from "@/lib/api";
import type { SystemStatus } from "@/lib/types";

import styles from "./HeaderStatus.module.css";

export function HeaderStatus() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const s = await getSystemStatus(controller.signal);
        if (!cancelled) {
          setStatus(s);
          setError(null);
        }
      } catch (err) {
        if (
          !cancelled &&
          !(err instanceof DOMException && err.name === "AbortError")
        ) {
          setError(err instanceof Error ? err.message : String(err));
          setStatus(null);
        }
      } finally {
        if (!cancelled) timer = setTimeout(tick, 15_000);
      }
    };

    void tick();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer !== null) clearTimeout(timer);
    };
  }, []);

  const healthy = status !== null && status.database_reachable && error === null;
  const label = error
    ? "API unreachable"
    : status
      ? `${status.app_name} · phase ${status.phase}`
      : "Checking…";

  return (
    <div className={styles.wrapper} title={error ?? status?.scope ?? ""}>
      <span
        className={`${styles.dot} ${healthy ? styles.healthy : styles.unhealthy}`}
        aria-hidden="true"
      />
      <span className={styles.label}>{label}</span>
    </div>
  );
}
