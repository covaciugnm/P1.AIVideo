"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { autoDetectBackendBaseUrl } from "@/lib/api";
import * as logBus from "@/lib/log-bus";
import {
  DEFAULT_SETTINGS,
  loadSettings,
  saveSettings,
  type Settings,
} from "@/lib/settings";

interface SettingsContextValue {
  readonly settings: Settings;
  readonly hydrated: boolean;
  readonly update: (patch: Partial<Settings>) => void;
  readonly reset: () => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { readonly children: ReactNode }) {
  // Start with defaults during SSR to avoid hydration mismatch; replace once
  // we know what's in localStorage on the client.
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const loaded = loadSettings();
    setSettings(loaded);
    setHydrated(true);
    logBus.emit({
      source: "frontend",
      level: "info",
      message: "settings loaded",
      meta: {
        apiBaseUrl: loaded.apiBaseUrl,
        url_source: loaded.apiBaseUrlIsCustom ? "user-override" : "default",
        backendHostPort: loaded.backendHostPort,
        frontendHostPort: loaded.frontendHostPort,
      },
    });

    // Phase 14C / 15X — auto-detect a reachable backend at page load.
    // Always runs (even if the operator pinned a custom URL) but the
    // custom URL is tried FIRST so a working operator override wins.
    // Order: same-host context first (matches the user's current
    // browsing origin), then the tunnel sibling host, then the
    // build-time URL, then localhost dev fallbacks. Whichever responds
    // to /healthz in 2.5s wins.

    const candidates: string[] = [];

    // 0. Operator override — try it first if pinned.
    if (loaded.apiBaseUrlIsCustom && loaded.apiBaseUrl) {
      candidates.push(loaded.apiBaseUrl);
    }

    if (typeof window !== "undefined") {
      const origin = window.location.origin;
      const host = window.location.hostname;
      const isLocalhost =
        host === "localhost"
        || host === "127.0.0.1"
        || host.startsWith("192.168.")
        || host.startsWith("10.")
        || host.endsWith(".local");

      if (isLocalhost) {
        // 1a. Localhost browsing → backend is also localhost, on the
        //     compose-published port (host 8001 by default).
        candidates.push(`http://${host}:${loaded.backendHostPort || 8001}`);
        candidates.push(`http://${host}:8001`);
        candidates.push(`http://${host}:8000`);
      } else {
        // 1b. Tunneled / domain browsing → the API sibling subdomain.
        try {
          const u = new URL(origin);
          if (u.hostname && !u.hostname.startsWith("api-")) {
            candidates.push(`${u.protocol}//api-${u.hostname}`);
          }
        } catch {
          /* ignore */
        }
        // Same-origin (when CF path routing maps /api to backend).
        candidates.push(origin);
      }
    }

    // 2. The build-time NEXT_PUBLIC_API_BASE_URL — works when the page
    //    was rebuilt with a deploy-target URL baked in.
    if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) {
      candidates.push(process.env.NEXT_PUBLIC_API_BASE_URL);
    }

    // 3. Last-resort dev fallbacks (works on any localhost setup).
    candidates.push("http://localhost:8001");
    candidates.push("http://localhost:8000");

    let cancelled = false;
    void (async () => {
      const winner = await autoDetectBackendBaseUrl(candidates);
      if (cancelled) return;
      if (winner && winner !== loaded.apiBaseUrl) {
        logBus.emit({
          source: "frontend",
          level: "info",
          message: `auto-detect: switching API base URL → ${winner}`,
          meta: { previous: loaded.apiBaseUrl, candidates },
        });
        setSettings((prev) =>
          prev.apiBaseUrlIsCustom ? prev : { ...prev, apiBaseUrl: winner },
        );
        // Persist so subsequent reloads start with the working URL.
        const fresh = { ...loaded, apiBaseUrl: winner };
        saveSettings(fresh);
      } else if (winner) {
        logBus.emit({
          source: "frontend",
          level: "info",
          message: `auto-detect: current API base URL is reachable (${winner})`,
        });
      } else {
        logBus.emit({
          source: "frontend",
          level: "warning",
          message: `auto-detect: no candidate backend reachable — tried ${candidates.length}`,
          meta: { candidates },
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const update = useCallback((patch: Partial<Settings>) => {
    setSettings((prev) => {
      let next: Settings = { ...prev, ...patch };

      // If the user typed into the API URL field, remember that — so future
      // backendHostPort edits don't clobber the custom URL.
      if (patch.apiBaseUrl !== undefined && patch.apiBaseUrl !== prev.apiBaseUrl) {
        next = { ...next, apiBaseUrlIsCustom: true };
      }

      // Auto-link: editing backendHostPort should update the API URL when
      // the user hasn't manually overridden it.
      if (
        patch.backendHostPort !== undefined &&
        patch.backendHostPort !== prev.backendHostPort &&
        !next.apiBaseUrlIsCustom
      ) {
        next = { ...next, apiBaseUrl: `http://localhost:${patch.backendHostPort}` };
      }

      // Auto-link: frontendHostPort drives the displayed Frontend URL when
      // the operator hasn't set a custom one (URL matches the previous
      // host-port-derived pattern).
      if (
        patch.frontendHostPort !== undefined &&
        patch.frontendHostPort !== prev.frontendHostPort &&
        prev.frontendUrl === `http://localhost:${prev.frontendHostPort}`
      ) {
        next = { ...next, frontendUrl: `http://localhost:${patch.frontendHostPort}` };
      }

      saveSettings(next);

      if (next.apiBaseUrl !== prev.apiBaseUrl) {
        logBus.emit({
          source: "frontend",
          level: "info",
          message: `API base URL changed → ${next.apiBaseUrl}`,
          meta: {
            previous: prev.apiBaseUrl,
            custom: next.apiBaseUrlIsCustom,
            via: patch.backendHostPort !== undefined ? "port-edit" : "url-edit",
          },
        });
      }
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    saveSettings(DEFAULT_SETTINGS);
    setSettings(DEFAULT_SETTINGS);
    logBus.emit({
      source: "frontend",
      level: "info",
      message: "settings reset to defaults",
    });
  }, []);

  const value = useMemo<SettingsContextValue>(
    () => ({ settings, hydrated, update, reset }),
    [settings, hydrated, update, reset],
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (ctx === null) {
    throw new Error("useSettings must be used within a SettingsProvider");
  }
  return ctx;
}
