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
  HELP_ARTICLES,
  HELP_SECTIONS,
  getArticleBySlug,
  getArticlesBySection,
} from "@/lib/help/content";
import { searchHelp, type HelpSearchHit } from "@/lib/help/search";
import type { HelpArticle, HelpBlock } from "@/lib/help/types";

import { useHelp } from "./HelpContext";
import styles from "./HelpOverlay.module.css";

const SECTIONS_SORTED = [...HELP_SECTIONS].sort((a, b) => a.order - b.order);

export function HelpOverlay() {
  const help = useHelp();
  const article = useMemo(
    () => getArticleBySlug(help.slug) ?? HELP_ARTICLES[0],
    [help.slug]
  );

  if (!help.open) return null;

  return <Overlay article={article} />;
}

function Overlay({ article }: { readonly article: HelpArticle }) {
  const help = useHelp();
  const [query, setQuery] = useState("");
  const [resultsCursor, setResultsCursor] = useState(0);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);

  const hits: readonly HelpSearchHit[] = useMemo(
    () => searchHelp(query, 10),
    [query]
  );

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

  // Scroll back to top on article change.
  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [article.slug]);

  // Focus trap: keep tab inside the panel.
  const panelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const focusables = () =>
      panelRef.current?.querySelectorAll<HTMLElement>(
        'a, button, input, textarea, [tabindex]:not([tabindex="-1"])'
      ) ?? null;
    const onTab = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const list = focusables();
      if (!list || list.length === 0) return;
      const first = list[0];
      const last = list[list.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onTab);
    return () => window.removeEventListener("keydown", onTab);
  }, []);

  const onScrimClick = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) help.closeHelp();
    },
    [help]
  );

  const navigateAndClear = useCallback(
    (slug: string) => {
      help.navigate(slug);
      setQuery("");
      setResultsCursor(0);
    },
    [help]
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
        if (target) navigateAndClear(target.article.slug);
      }
    },
    [hits, resultsCursor, navigateAndClear]
  );

  return (
    <div
      className={styles.scrim}
      onClick={onScrimClick}
      role="dialog"
      aria-modal="true"
      aria-label="Help"
    >
      <div className={styles.panel} ref={panelRef}>
        <div className={styles.topbar}>
          <span className={styles.title}>
            <span className={styles.titleAccent}>?</span> P1.AIVideo Help
          </span>
          <div className={styles.navBtns}>
            <button
              type="button"
              className={styles.iconBtn}
              onClick={() => help.back()}
              disabled={!help.canGoBack}
              aria-label="Go back"
              title="Back"
            >
              ←
            </button>
            <button
              type="button"
              className={styles.iconBtn}
              onClick={() => help.forward()}
              disabled={!help.canGoForward}
              aria-label="Go forward"
              title="Forward"
            >
              →
            </button>
          </div>
          <div className={styles.search}>
            <span className={styles.searchIcon} aria-hidden>
              ⌕
            </span>
            <input
              ref={searchRef}
              type="search"
              placeholder="Search help… (press / to focus)"
              className={styles.searchInput}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setResultsCursor(0);
              }}
              onKeyDown={onSearchKey}
              aria-label="Search help"
              spellCheck={false}
              autoComplete="off"
            />
            {query.length === 0 ? (
              <kbd className={styles.searchKbd}>/</kbd>
            ) : null}
            {query.trim().length > 0 ? (
              <div className={styles.searchResults} role="listbox">
                {hits.length === 0 ? (
                  <div className={styles.searchEmpty}>
                    No matches. Try a less specific query, or browse by section.
                  </div>
                ) : (
                  hits.map((hit, i) => (
                    <button
                      key={hit.article.slug}
                      type="button"
                      className={`${styles.searchHit} ${i === resultsCursor ? styles.searchHitActive : ""}`}
                      onMouseEnter={() => setResultsCursor(i)}
                      onClick={() => navigateAndClear(hit.article.slug)}
                      role="option"
                      aria-selected={i === resultsCursor}
                    >
                      <div className={styles.searchHitTitle}>
                        {hit.article.title}
                      </div>
                      <div className={styles.searchHitMeta}>
                        {sectionTitle(hit.article.section)} ·{" "}
                        {hit.matchedIn.join(", ")} · score {hit.score}
                      </div>
                      <div className={styles.searchHitSummary}>
                        {hit.article.summary}
                      </div>
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
            aria-label="Close help"
          >
            Close <kbd className={styles.searchKbd}>Esc</kbd>
          </button>
        </div>

        <nav className={styles.nav} aria-label="Help sections">
          {SECTIONS_SORTED.map((section) => {
            const items = getArticlesBySection(section.id);
            if (items.length === 0) return null;
            return (
              <div key={section.id} className={styles.section}>
                <div className={styles.sectionLabel}>{section.title}</div>
                {section.description ? (
                  <div className={styles.sectionDescription}>
                    {section.description}
                  </div>
                ) : null}
                {items.map((a) => (
                  <button
                    key={a.slug}
                    type="button"
                    className={`${styles.articleLink} ${a.slug === article.slug ? styles.articleLinkActive : ""}`}
                    onClick={() => help.navigate(a.slug)}
                  >
                    {a.title}
                  </button>
                ))}
              </div>
            );
          })}
        </nav>

        <div className={styles.content} ref={contentRef}>
          <article className={styles.article}>
            <div className={styles.articleEyebrow}>
              {sectionTitle(article.section)}
            </div>
            <h1 className={styles.articleTitle}>{article.title}</h1>
            <div className={styles.articleSummary}>{article.summary}</div>
            {article.body.map((block, i) => (
              <BlockRenderer
                key={`${article.slug}-${i}`}
                block={block}
                onNavigate={help.navigate}
              />
            ))}
            {article.related && article.related.length > 0 ? (
              <div className={styles.articleFooter}>
                <div className={styles.relatedHeading}>Related</div>
                <div className={styles.related}>
                  {article.related.map((slug) => {
                    const r = getArticleBySlug(slug);
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

function sectionTitle(id: string): string {
  return HELP_SECTIONS.find((s) => s.id === id)?.title ?? id;
}

function BlockRenderer({
  block,
  onNavigate,
}: {
  readonly block: HelpBlock;
  readonly onNavigate: (slug: string) => void;
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
              <li key={i}>
                {it.map((sub, j) => (
                  <span key={j}>{sub}</span>
                ))}
              </li>
            ) : (
              <li key={i}>{it as string}</li>
            )
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
      const target = getArticleBySlug(block.slug);
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
