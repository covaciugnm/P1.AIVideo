"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from "react";

import {
  getLocalizedHelpCorpus,
  type HelpTopic,
} from "@/lib/help/dictionaries";
import type { HelpBlock } from "@/lib/help/types";
import { useLanguage, useT } from "@/lib/i18n/LanguageContext";

import { useHelp } from "./HelpContext";
import styles from "./HelpOverlay.module.css";

export function HelpOverlay() {
  const help = useHelp();
  const { language } = useLanguage();
  const corpus = useMemo(() => getLocalizedHelpCorpus(language), [language]);
  const topic: HelpTopic = useMemo(() => {
    return (
      corpus[help.slug] ??
      corpus["dashboard"] ??
      Object.values(corpus)[0]
    );
  }, [corpus, help.slug]);

  if (!help.open) return null;
  return <Overlay topic={topic} corpus={corpus} />;
}

function Overlay({
  topic,
  corpus,
}: {
  readonly topic: HelpTopic;
  readonly corpus: Readonly<Record<string, HelpTopic>>;
}) {
  const help = useHelp();
  const t = useT();
  const [query, setQuery] = useState("");
  const [resultsCursor, setResultsCursor] = useState(0);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);

  const sections = useMemo(() => {
    const groups = new Map<string, HelpTopic[]>();
    for (const t of Object.values(corpus)) {
      const arr = groups.get(t.section) ?? [];
      arr.push(t);
      groups.set(t.section, arr);
    }
    return [...groups.entries()].map(([name, items]) => ({ name, items }));
  }, [corpus]);

  const hits = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [] as HelpTopic[];
    const matches: { topic: HelpTopic; score: number }[] = [];
    for (const top of Object.values(corpus)) {
      const haystack = (
        top.title +
        " " +
        top.summary +
        " " +
        top.id +
        " " +
        top.body
          .map((b) => {
            if (b.type === "p" || b.type === "h") return b.text;
            if (b.type === "kv")
              return b.rows.map(([k, v]) => `${k} ${v}`).join(" ");
            if (b.type === "list")
              return b.items.map((it) => (Array.isArray(it) ? it.join(" ") : it)).join(" ");
            if (b.type === "callout") return (b.title ?? "") + " " + b.text;
            if (b.type === "code") return (b.caption ?? "") + " " + b.text;
            return "";
          })
          .join(" ")
      ).toLowerCase();
      const needles = q.split(/\s+/).filter(Boolean);
      let score = 0;
      for (const n of needles) if (haystack.includes(n)) score += 1;
      if (score > 0) matches.push({ topic: top, score });
    }
    return matches
      .sort((a, b) => b.score - a.score)
      .slice(0, 10)
      .map((m) => m.topic);
  }, [query, corpus]);

  // Focus search with `/` while overlay is open.
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "/" && document.activeElement !== searchRef.current) {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Scroll to top on topic change.
  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0 });
  }, [topic.id]);

  const onScrimClick = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) help.closeHelp();
    },
    [help],
  );

  const navigateAndClear = useCallback(
    (slug: string) => {
      help.navigate(slug);
      setQuery("");
      setResultsCursor(0);
    },
    [help],
  );

  const onSearchKey = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (hits.length === 0) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setResultsCursor((c) => Math.min(c + 1, hits.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setResultsCursor((c) => Math.max(c - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const target = hits[resultsCursor];
        if (target) navigateAndClear(target.id);
      }
    },
    [hits, resultsCursor, navigateAndClear],
  );

  return (
    <div
      className={styles.scrim}
      onClick={onScrimClick}
      role="dialog"
      aria-modal="true"
      aria-label={t("help.open")}
    >
      <div className={styles.panel}>
        <div className={styles.topbar}>
          <span className={styles.title}>
            <span className={styles.titleAccent}>?</span> P1.AIVideo {t("nav.help")}
          </span>
          <div className={styles.navBtns}>
            <button
              type="button"
              className={styles.iconBtn}
              onClick={() => help.back()}
              disabled={!help.canGoBack}
              aria-label={t("common.back")}
              title={t("common.back")}
            >
              ←
            </button>
            <button
              type="button"
              className={styles.iconBtn}
              onClick={() => help.forward()}
              disabled={!help.canGoForward}
              aria-label={t("common.forward")}
              title={t("common.forward")}
            >
              →
            </button>
          </div>
          <div className={styles.search}>
            <span className={styles.searchIcon} aria-hidden>⌕</span>
            <input
              ref={searchRef}
              type="search"
              placeholder={t("help.searchPlaceholder")}
              className={styles.searchInput}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setResultsCursor(0);
              }}
              onKeyDown={onSearchKey}
              aria-label={t("help.search")}
              spellCheck={false}
              autoComplete="off"
            />
            {query.length === 0 ? (
              <kbd className={styles.searchKbd}>/</kbd>
            ) : null}
            {query.trim().length > 0 ? (
              <div className={styles.searchResults} role="listbox">
                {hits.length === 0 ? (
                  <div className={styles.searchEmpty}>{t("help.noResults")}</div>
                ) : (
                  hits.map((hit, i) => (
                    <button
                      key={hit.id}
                      type="button"
                      className={`${styles.searchHit} ${i === resultsCursor ? styles.searchHitActive : ""}`}
                      onMouseEnter={() => setResultsCursor(i)}
                      onClick={() => navigateAndClear(hit.id)}
                      role="option"
                      aria-selected={i === resultsCursor}
                    >
                      <div className={styles.searchHitTitle}>{hit.title}</div>
                      <div className={styles.searchHitMeta}>{hit.section}</div>
                      <div className={styles.searchHitSummary}>{hit.summary}</div>
                    </button>
                  ))
                )}
              </div>
            ) : null}
          </div>
          <button
            type="button"
            className={styles.close}
            onClick={() => help.closeHelp()}
            aria-label={t("help.close")}
          >
            {t("common.close")} <kbd className={styles.searchKbd}>Esc</kbd>
          </button>
        </div>

        <nav className={styles.nav} aria-label={t("help.open")}>
          {sections.map((section) => (
            <div key={section.name} className={styles.section}>
              <div className={styles.sectionLabel}>{section.name}</div>
              {section.items.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  className={`${styles.articleLink} ${a.id === topic.id ? styles.articleLinkActive : ""}`}
                  onClick={() => help.navigate(a.id)}
                >
                  {a.title}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className={styles.content} ref={contentRef}>
          <article className={styles.article}>
            <div className={styles.articleEyebrow}>{topic.section}</div>
            <h1 className={styles.articleTitle}>{topic.title}</h1>
            <div className={styles.articleSummary}>{topic.summary}</div>
            {topic.body.map((block, i) => (
              <BlockRenderer
                key={`${topic.id}-${i}`}
                block={block}
                onNavigate={help.navigate}
                corpus={corpus}
              />
            ))}
            {topic.related && topic.related.length > 0 ? (
              <div className={styles.articleFooter}>
                <div className={styles.relatedHeading}>{t("help.related")}</div>
                <div className={styles.related}>
                  {topic.related.map((slug) => {
                    const r = corpus[slug];
                    if (!r) return null;
                    return (
                      <button
                        key={slug}
                        type="button"
                        className={styles.relatedChip}
                        onClick={() => help.navigate(slug)}
                      >
                        {r.title}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </article>
        </div>
      </div>
    </div>
  );
}

function BlockRenderer({
  block,
  onNavigate,
  corpus,
}: {
  readonly block: HelpBlock;
  readonly onNavigate: (slug: string) => void;
  readonly corpus: Readonly<Record<string, HelpTopic>>;
}) {
  switch (block.type) {
    case "p":
      return <p>{block.text}</p>;
    case "h":
      if (block.level === 2) return <h2>{block.text}</h2>;
      if (block.level === 3) return <h3>{block.text}</h3>;
      return <h4>{block.text}</h4>;
    case "code":
      return (
        <>
          <pre>
            <code>{block.text}</code>
          </pre>
          {block.caption ? (
            <div className={styles.codeCaption}>{block.caption}</div>
          ) : null}
        </>
      );
    case "list": {
      const Tag = block.ordered ? "ol" : "ul";
      return (
        <Tag className={styles.list}>
          {block.items.map((it, i) =>
            Array.isArray(it) ? (
              <li key={i}>{(it as readonly string[]).join(" ")}</li>
            ) : (
              <li key={i}>{it as string}</li>
            ),
          )}
        </Tag>
      );
    }
    case "kv":
      return (
        <>
          {block.caption ? (
            <div className={styles.kvCaption}>{block.caption}</div>
          ) : null}
          <table className={styles.kvTable}>
            <tbody>
              {block.rows.map(([k, v], i) => (
                <tr key={i}>
                  <th>{k}</th>
                  <td>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      );
    case "callout": {
      const toneClass =
        block.tone === "warn"
          ? styles.calloutWarn
          : block.tone === "danger"
            ? styles.calloutDanger
            : block.tone === "success"
              ? styles.calloutSuccess
              : styles.calloutInfo;
      return (
        <div className={`${styles.callout} ${toneClass}`}>
          {block.title ? (
            <strong className={styles.calloutTitle}>{block.title}</strong>
          ) : null}
          {block.text}
        </div>
      );
    }
    case "link":
      return (
        <p>
          <a href={block.href} target="_blank" rel="noreferrer noopener">
            {block.text}
          </a>
        </p>
      );
    case "linkArticle": {
      const target = corpus[block.slug];
      if (!target) return null;
      return (
        <button
          type="button"
          className={styles.articleLinkBlock}
          onClick={() => onNavigate(block.slug)}
        >
          {block.label ?? target.title}
        </button>
      );
    }
    case "spacer":
      return <div style={{ height: "var(--space-3)" }} />;
  }
}
