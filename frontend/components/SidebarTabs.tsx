"use client";

import type { SidebarTabId } from "@/lib/settings";

import styles from "./SidebarTabs.module.css";

// Re-export so existing imports of ``SidebarTab`` from this module keep
// working alongside the canonical ``SidebarTabId`` in lib/settings.
export type SidebarTab = SidebarTabId;

interface SidebarTabsProps {
  readonly active: SidebarTab;
  readonly onChange: (tab: SidebarTab) => void;
}

const _TABS: readonly { id: SidebarTab; label: string }[] = [
  { id: "logs", label: "Logs" },
  { id: "settings", label: "Settings" },
  // Phase 8F-2 — operator provider diagnostics.
  { id: "test1", label: "Test1" },
];

export function SidebarTabs({ active, onChange }: SidebarTabsProps) {
  return (
    <div className={styles.tabs} role="tablist">
      {_TABS.map((tab) => (
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
