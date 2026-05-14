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
      meta: { apiBaseUrl: loaded.apiBaseUrl },
    });
  }, []);

  const update = useCallback((patch: Partial<Settings>) => {
    setSettings((prev) => {
      const next: Settings = { ...prev, ...patch };
      saveSettings(next);
      if (patch.apiBaseUrl && patch.apiBaseUrl !== prev.apiBaseUrl) {
        logBus.emit({
          source: "frontend",
          level: "info",
          message: `API base URL changed → ${patch.apiBaseUrl}`,
          meta: { previous: prev.apiBaseUrl },
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
