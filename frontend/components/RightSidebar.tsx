"use client";

import { useEffect, useState } from "react";

import {
  DEFAULT_SIDEBAR_STATE,
  loadSidebarState,
  saveSidebarState,
  type SidebarState,
} from "@/lib/settings";

import { useT } from "@/lib/i18n/LanguageContext";

import { BackendLogsPanel } from "./BackendLogsPanel";
import { KeysPanel } from "./KeysPanel";
import { LogsPanel } from "./LogsPanel";
import { ProviderTestPanel } from "./ProviderTestPanel";
import { SettingsPanel } from "./SettingsPanel";
import { SidebarTabs } from "./SidebarTabs";
import styles from "./RightSidebar.module.css";

export function RightSidebar() {
  const t = useT();
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
      aria-label={t("sidebar.activity")}
    >
      <div className={styles.header}>
        <button
          type="button"
          className={styles.toggle}
          onClick={toggle}
          aria-label={collapsed ? t("sidebar.expand") : t("sidebar.collapse")}
          title={collapsed ? t("sidebar.expand") : t("sidebar.collapse")}
        >
          {collapsed ? "«" : "»"}
        </button>
        {!collapsed && <span className={styles.title}>{t("sidebar.activity")}</span>}
      </div>

      {collapsed ? (
        <div className={styles.rail}>
          <button
            type="button"
            className={`${styles.railTab} ${state.activeTab === "logs" ? styles.railTabActive : ""}`}
            onClick={() => update({ collapsed: false, activeTab: "logs" })}
            title={t("sidebar.logs")}
          >
            <span className={styles.railLabel}>{t("sidebar.logs")}</span>
          </button>
          <button
            type="button"
            className={`${styles.railTab} ${state.activeTab === "backend" ? styles.railTabActive : ""}`}
            onClick={() => update({ collapsed: false, activeTab: "backend" })}
            title={t("sidebar.backend")}
          >
            <span className={styles.railLabel}>{t("sidebar.backend")}</span>
          </button>
          <button
            type="button"
            className={`${styles.railTab} ${state.activeTab === "settings" ? styles.railTabActive : ""}`}
            onClick={() => update({ collapsed: false, activeTab: "settings" })}
            title={t("sidebar.settings")}
          >
            <span className={styles.railLabel}>{t("sidebar.settings")}</span>
          </button>
          <button
            type="button"
            className={`${styles.railTab} ${state.activeTab === "test1" ? styles.railTabActive : ""}`}
            onClick={() => update({ collapsed: false, activeTab: "test1" })}
            title={t("badges.test1Description")}
          >
            <span className={styles.railLabel}>{t("sidebar.test1")}</span>
          </button>
          <button
            type="button"
            className={`${styles.railTab} ${state.activeTab === "keys" ? styles.railTabActive : ""}`}
            onClick={() => update({ collapsed: false, activeTab: "keys" })}
            title={t("sidebar.keys")}
          >
            <span className={styles.railLabel}>{t("sidebar.keys")}</span>
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
            {hydrated && state.activeTab === "backend" && <BackendLogsPanel />}
            {hydrated && state.activeTab === "settings" && <SettingsPanel />}
            {hydrated && state.activeTab === "test1" && <ProviderTestPanel />}
            {hydrated && state.activeTab === "keys" && <KeysPanel />}
          </div>
        </>
      )}
    </aside>
  );
}
