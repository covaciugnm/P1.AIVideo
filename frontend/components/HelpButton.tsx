"use client";

import { useHelp } from "./HelpContext";
import styles from "./HelpButton.module.css";

export function HelpButton() {
  const help = useHelp();

  if (help.open) return null;

  return (
    <button
      type="button"
      className={styles.fab}
      onClick={() => help.openHelp()}
      aria-label="Open help (press ? at any time)"
      title="Open help — press ? at any time"
    >
      <span aria-hidden className={styles.glyph}>
        ?
      </span>
      <span className={styles.label}>Help</span>
      <kbd className={styles.kbd}>?</kbd>
    </button>
  );
}
