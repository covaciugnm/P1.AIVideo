"use client";

import type { ReactNode } from "react";

import { LogsProvider } from "./LogsContext";
import { SettingsProvider } from "./SettingsContext";

export function Providers({ children }: { readonly children: ReactNode }) {
  return (
    <SettingsProvider>
      <LogsProvider>{children}</LogsProvider>
    </SettingsProvider>
  );
}
