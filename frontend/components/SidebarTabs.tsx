"use client";

import { useT } from "@/lib/i18n/LanguageContext";
import type { SidebarTabId } from "@/lib/settings";

import styles from "./SidebarTabs.module.css";

// Re-export so existing imports of ``SidebarTab`` from this module keep
// working alongside the canonical ``SidebarTabId`` in lib/settings.
export type SidebarTab = SidebarTabId;

interface SidebarTabsProps {
  readonly active: SidebarTab;
  readonly onChange: (tab: SidebarTab) => void;
}

export function SidebarTabs({ active, onChange }: SidebarTabsProps) {
  const t = useT();
  const tabs: readonly { id: SidebarTab; label: string }[] = [
    { id: "logs", label: t("sidebar.logs") },
    // Phase 13 — live tail of backend INFO/progress logs.
    { id: "backend", label: t("sidebar.backend") },
    { id: "settings", label: t("sidebar.settings") },
    // Phase 8F-2 — operator provider diagnostics.
    { id: "test1", label: t("sidebar.test1") },
    // Phase 12X — DB-backed API keys store + test probes.
    { id: "keys", label: t("sidebar.keys") },
  ];
  return (
    <div className={styles.tabs} role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          className={`${styles.tab} ${active === tab.id ? styles.tabActive : ""}`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
