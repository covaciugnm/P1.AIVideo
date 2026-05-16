"use client";

import type { ReactNode } from "react";

import { HelpProvider } from "./HelpContext";
import { LogsProvider } from "./LogsContext";
import { SettingsProvider } from "./SettingsContext";

export function Providers({ children }: { readonly children: ReactNode }) {
  return (
    <SettingsProvider>
      <LogsProvider>
        <HelpProvider>{children}</HelpProvider>
      </LogsProvider>
    </SettingsProvider>
  );
}
