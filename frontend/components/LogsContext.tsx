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
import type { LogEntry } from "@/lib/log-bus";

import { useSettings } from "./SettingsContext";

interface LogsContextValue {
  readonly entries: readonly LogEntry[];
  readonly clear: () => void;
  readonly log: (input: Omit<LogEntry, "id" | "timestamp">) => void;
}

const LogsContext = createContext<LogsContextValue | null>(null);

export function LogsProvider({ children }: { readonly children: ReactNode }) {
  const { settings } = useSettings();
  const [entries, setEntries] = useState<readonly LogEntry[]>([]);
  const maxEntries = settings.maxLogEntries;

  useEffect(() => {
    const unsubscribe = logBus.subscribe((entry) => {
      setEntries((prev) => {
        const next = [entry, ...prev];
        if (next.length > maxEntries) {
          next.length = maxEntries;
        }
        return next;
      });
    });
    return unsubscribe;
  }, [maxEntries]);

  useEffect(() => {
    setEntries((prev) => {
      if (prev.length <= maxEntries) return prev;
      return prev.slice(0, maxEntries);
    });
  }, [maxEntries]);

  const clear = useCallback(() => {
    setEntries([]);
    logBus.emit({
      source: "frontend",
      level: "info",
      message: "logs cleared",
    });
  }, []);

  const log = useCallback((input: Omit<LogEntry, "id" | "timestamp">) => {
    logBus.emit(input);
  }, []);

  const value = useMemo<LogsContextValue>(
    () => ({ entries, clear, log }),
    [entries, clear, log],
  );

  return <LogsContext.Provider value={value}>{children}</LogsContext.Provider>;
}

export function useLogs(): LogsContextValue {
  const ctx = useContext(LogsContext);
  if (ctx === null) {
    throw new Error("useLogs must be used within a LogsProvider");
  }
  return ctx;
}
