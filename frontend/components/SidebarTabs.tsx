"use client";

import styles from "./SidebarTabs.module.css";

export type SidebarTab = "logs" | "settings";

interface SidebarTabsProps {
  readonly active: SidebarTab;
  readonly onChange: (tab: SidebarTab) => void;
}

export function SidebarTabs({ active, onChange }: SidebarTabsProps) {
  return (
    <div className={styles.tabs} role="tablist">
      <button
        type="button"
        role="tab"
        aria-selected={active === "logs"}
        className={`${styles.tab} ${active === "logs" ? styles.tabActive : ""}`}
        onClick={() => onChange("logs")}
      >
        Logs
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={active === "settings"}
        className={`${styles.tab} ${active === "settings" ? styles.tabActive : ""}`}
        onClick={() => onChange("settings")}
      >
        Settings
      </button>
    </div>
  );
}
