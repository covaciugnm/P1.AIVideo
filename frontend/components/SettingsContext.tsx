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
