"use client";

import { getHelpTopic } from "@/lib/help/dictionaries";
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
  const topic = getHelpTopic(language, slug);
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
