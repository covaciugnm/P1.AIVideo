"use client";

import { useEffect, useRef } from "react";

import { HelpHint } from "@/components/HelpHint";
import { SettingsPanel } from "@/components/SettingsPanel";
import { useT } from "@/lib/i18n/LanguageContext";
import * as logBus from "@/lib/log-bus";

import styles from "./page.module.css";

export default function SettingsPage() {
  const t = useT();
  const announcedRef = useRef(false);

  useEffect(() => {
    if (!announcedRef.current) {
      announcedRef.current = true;
      logBus.emit({
        source: "frontend",
        level: "info",
        message: "settings page opened",
      });
    }
  }, []);

  return (
    <div>
      <h1>
        {t("settings.title")}
        <HelpHint slug="settings" />
      </h1>
      <p className="muted">{t("settings.intro")}</p>
      <div className={styles.fullPanel}>
        <SettingsPanel />
      </div>
    </div>
  );
}
