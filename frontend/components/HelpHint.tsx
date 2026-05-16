"use client";

import { useHelp } from "./HelpContext";
import { getArticleBySlug } from "@/lib/help/content";
import styles from "./HelpHint.module.css";

/** Inline `?` chip that opens the help overlay at a specific article. */
export function HelpHint({
  slug,
  label,
  small,
}: {
  readonly slug: string;
  /** Accessible label override. Defaults to "Help: <article title>". */
  readonly label?: string;
  /** Smaller variant for tight inline spots. */
  readonly small?: boolean;
}) {
  const help = useHelp();
  const article = getArticleBySlug(slug);
  const title = label ?? (article ? `Help: ${article.title}` : "Help");
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
      {children ?? "Help"}
    </button>
  );
}
