"use client";

import { useEffect, useRef } from "react";

import { HelpHint } from "@/components/HelpHint";
import { SettingsPanel } from "@/components/SettingsPanel";
import * as logBus from "@/lib/log-bus";

import styles from "./page.module.css";

export default function SettingsPage() {
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
        Settings
        <HelpHint slug="page-settings" />
      </h1>
      <p className="muted">
        These settings live in your browser only (localStorage). Reset clears
        every override and reverts to the build-time defaults.
      </p>
      <div className={styles.fullPanel}>
        <SettingsPanel />
      </div>
    </div>
  );
}
