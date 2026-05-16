"use client";

import { useEffect, useState } from "react";

import {
  DEFAULT_SIDEBAR_STATE,
  loadSidebarState,
  saveSidebarState,
  type SidebarState,
} from "@/lib/settings";

import { LogsPanel } from "./LogsPanel";
import { ProviderTestPanel } from "./ProviderTestPanel";
import { SettingsPanel } from "./SettingsPanel";
import { SidebarTabs } from "./SidebarTabs";
import styles from "./RightSidebar.module.css";

export function RightSidebar() {
  const [state, setState] = useState<SidebarState>(DEFAULT_SIDEBAR_STATE);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setState(loadSidebarState());
    setHydrated(true);
  }, []);

  const update = (patch: Partial<SidebarState>) => {
    setState((prev) => {
      const next: SidebarState = { ...prev, ...patch };
      saveSidebarState(next);
      return next;
    });
  };

  const toggle = () => update({ collapsed: !state.collapsed });

  // Avoid rendering the panel content during SSR — it would briefly show
  // the default open state before localStorage hydration. The collapsed
  // attribute on the root is enough to drive CSS during the first paint.
  const collapsed = state.collapsed;

  return (
    <aside
      className={`${styles.sidebar} ${collapsed ? styles.collapsed : styles.expanded}`}
      aria-label="Activity sidebar"
    >
      <div className={styles.header}>
        <button
          type="button"
          className={styles.toggle}
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? "«" : "»"}
        </button>
        {!collapsed && <span className={styles.title}>Activity</span>}
      </div>

      {collapsed ? (
        <div className={styles.rail}>
          <button
            type="button"
            className={`${styles.railTab} ${state.activeTab === "logs" ? styles.railTabActive : ""}`}
            onClick={() => update({ collapsed: false, activeTab: "logs" })}
            title="Logs"
          >
            <span className={styles.railLabel}>Logs</span>
          </button>
          <button
            type="button"
            className={`${styles.railTab} ${state.activeTab === "settings" ? styles.railTabActive : ""}`}
            onClick={() => update({ collapsed: false, activeTab: "settings" })}
            title="Settings"
          >
            <span className={styles.railLabel}>Settings</span>
          </button>
          <button
            type="button"
            className={`${styles.railTab} ${state.activeTab === "test1" ? styles.railTabActive : ""}`}
            onClick={() => update({ collapsed: false, activeTab: "test1" })}
            title="Test1 — provider diagnostics"
          >
            <span className={styles.railLabel}>Test1</span>
          </button>
        </div>
      ) : (
        <>
          <SidebarTabs
            active={state.activeTab}
            onChange={(tab) => update({ activeTab: tab })}
          />
          <div className={styles.body}>
            {hydrated && state.activeTab === "logs" && <LogsPanel />}
            {hydrated && state.activeTab === "settings" && <SettingsPanel />}
            {hydrated && state.activeTab === "test1" && <ProviderTestPanel />}
          </div>
        </>
      )}
    </aside>
  );
}
