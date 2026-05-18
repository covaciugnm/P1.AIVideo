"use client";

import { getLocalizedHelpCorpus } from "@/lib/help/dictionaries";
import { useLanguage, useT } from "@/lib/i18n/LanguageContext";

import { useHelp } from "./HelpContext";
import styles from "./HelpHint.module.css";

/** Inline `?` chip that opens the help overlay at a specific topic. */
export function HelpHint({
  slug,
  label,
  small,
}: {
  readonly slug: string;
  /** Accessible label override. Defaults to "<help.open>: <topic title>". */
  readonly label?: string;
  /** Smaller variant for tight inline spots. */
  readonly small?: boolean;
}) {
  const help = useHelp();
  const t = useT();
  const { language } = useLanguage();
  // Phase 12 — read directly from the CURRENT language's corpus. The
  // older getHelpTopic() helper falls back to the English entry when a
  // RO topic is missing, which caused tooltips to leak English titles
  // (bug reported by the operator). Now: if the topic doesn't exist in
  // the selected language, we render the generic localized
  // ``t("help.open")`` instead of an English title — and log it in dev
  // so the missing translation can be added.
  const corpus = getLocalizedHelpCorpus(language);
  const topic = corpus[slug];
  if (!topic && process.env.NODE_ENV !== "production") {
    // eslint-disable-next-line no-console
    console.warn(
      `[HelpHint] missing topic "${slug}" in language "${language}" — add it to frontend/lib/help/dictionaries/${language}.ts`,
    );
  }
  const title = label ?? (topic ? `${t("help.open")}: ${topic.title}` : t("help.open"));
  return (
    <button
      type="button"
      className={`${styles.hint} ${small ? styles.hintInline : ""}`}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        help.openHelp(slug);
      }}
      aria-label={title}
      title={title}
    >
      ?
    </button>
  );
}

/** Standalone "Help →" link, used in headers / footers. */
export function HelpLink({
  slug,
  children,
  className,
}: {
  readonly slug?: string;
  readonly children?: React.ReactNode;
  readonly className?: string;
}) {
  const help = useHelp();
  const t = useT();
  return (
    <button
      type="button"
      className={className}
      onClick={() => help.openHelp(slug)}
      style={{
        background: "transparent",
        border: "none",
        padding: 0,
        color: "inherit",
        cursor: "pointer",
        font: "inherit",
      }}
    >
      {children ?? t("nav.help")}
    </button>
  );
}
