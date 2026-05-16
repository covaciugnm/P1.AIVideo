"use client";

import type { ReactNode } from "react";

import { LanguageProvider } from "@/lib/i18n/LanguageContext";

import { HelpProvider } from "./HelpContext";
import { LogsProvider } from "./LogsContext";
import { SettingsProvider } from "./SettingsContext";

export function Providers({ children }: { readonly children: ReactNode }) {
  return (
    <SettingsProvider>
      <LanguageProvider>
        <LogsProvider>
          <HelpProvider>{children}</HelpProvider>
        </LogsProvider>
      </LanguageProvider>
    </SettingsProvider>
  );
}
