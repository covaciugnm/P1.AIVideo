"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { HelpHint } from "@/components/HelpHint";
import {
  getTechnicalArchitecture,
  getTechnicalArchitectureMarkdownUrl,
  type TechnicalArchitectureResponse,
} from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageContext";
import * as logBus from "@/lib/log-bus";

import styles from "./page.module.css";

type Block =
  | { kind: "h"; level: 1 | 2 | 3 | 4; text: string; anchor: string }
  | { kind: "p"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "code"; text: string }
  | { kind: "table"; headers: string[]; rows: string[][] }
  | { kind: "hr" }
  | { kind: "quote"; text: string };

function anchorFor(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s\-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
}

function parseMarkdown(md: string): Block[] {
  const blocks: Block[] = [];
  const lines = md.split(/\r?\n/);
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") {
      i += 1;
      continue;
    }
    if (line.startsWith("```")) {
      const buf: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) {
        buf.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push({ kind: "code", text: buf.join("\n") });
      continue;
    }
    if (line.startsWith("# ")) {
      const text = line.slice(2).trim();
      blocks.push({ kind: "h", level: 1, text, anchor: anchorFor(text) });
      i += 1;
      continue;
    }
    if (line.startsWith("## ")) {
      const text = line.slice(3).trim();
      blocks.push({ kind: "h", level: 2, text, anchor: anchorFor(text) });
      i += 1;
      continue;
    }
    if (line.startsWith("### ")) {
      const text = line.slice(4).trim();
      blocks.push({ kind: "h", level: 3, text, anchor: anchorFor(text) });
      i += 1;
      continue;
    }
    if (line.startsWith("#### ")) {
      const text = line.slice(5).trim();
      blocks.push({ kind: "h", level: 4, text, anchor: anchorFor(text) });
      i += 1;
      continue;
    }
    if (line.startsWith("> ")) {
      const buf: string[] = [];
      while (i < lines.length && lines[i].startsWith("> ")) {
        buf.push(lines[i].slice(2));
        i += 1;
      }
      blocks.push({ kind: "quote", text: buf.join(" ") });
      continue;
    }
    if (/^[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s/, "").trim());
        i += 1;
      }
      blocks.push({ kind: "ul", items });
      continue;
    }
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, "").trim());
        i += 1;
      }
      blocks.push({ kind: "ol", items });
      continue;
    }
    if (line.startsWith("|") && i + 1 < lines.length && /^\s*\|[\s\-:|]+\|\s*$/.test(lines[i + 1])) {
      const headers = line
        .split("|")
        .slice(1, -1)
        .map((c) => c.trim());
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        rows.push(
          lines[i]
            .split("|")
            .slice(1, -1)
            .map((c) => c.trim()),
        );
        i += 1;
      }
      blocks.push({ kind: "table", headers, rows });
      continue;
    }
    if (line.startsWith("---")) {
      blocks.push({ kind: "hr" });
      i += 1;
      continue;
    }
    const buf: string[] = [line];
    i += 1;
    while (i < lines.length && lines[i].trim() !== "" && !/^[#>|\-*`]/.test(lines[i]) && !/^\d+\.\s/.test(lines[i])) {
      buf.push(lines[i]);
      i += 1;
    }
    blocks.push({ kind: "p", text: buf.join(" ") });
  }
  return blocks;
}

function renderInline(text: string, highlight: string): React.ReactNode {
  // Escape, then linkify [a](b), then code `…`, then bold **…**.
  // Build nodes via a single pass for simplicity, then highlight matches.
  const nodes: React.ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={`b-${match.index}`}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(<code key={`c-${match.index}`}>{token.slice(1, -1)}</code>);
    } else {
      const inner = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (inner) {
        nodes.push(
          <a key={`a-${match.index}`} href={inner[2]} target="_blank" rel="noreferrer">
            {inner[1]}
          </a>,
        );
      }
    }
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  if (!highlight) return nodes;
  const lower = highlight.toLowerCase();
  return nodes.flatMap((node, idx) => {
    if (typeof node !== "string") return [node];
    const parts: React.ReactNode[] = [];
    let cursor = 0;
    const lowerText = node.toLowerCase();
    while (cursor < node.length) {
      const found = lowerText.indexOf(lower, cursor);
      if (found === -1) {
        parts.push(node.slice(cursor));
        break;
      }
      if (found > cursor) parts.push(node.slice(cursor, found));
      parts.push(
        <mark key={`m-${idx}-${found}`} className={styles.highlight}>
          {node.slice(found, found + highlight.length)}
        </mark>,
      );
      cursor = found + highlight.length;
    }
    return parts;
  });
}

function blockMatchesQuery(block: Block, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  if (block.kind === "h" || block.kind === "p" || block.kind === "code" || block.kind === "quote") {
    return block.text.toLowerCase().includes(needle);
  }
  if (block.kind === "ul" || block.kind === "ol") {
    return block.items.some((item) => item.toLowerCase().includes(needle));
  }
  if (block.kind === "table") {
    return (
      block.headers.some((h) => h.toLowerCase().includes(needle)) ||
      block.rows.some((row) => row.some((cell) => cell.toLowerCase().includes(needle)))
    );
  }
  return false;
}

function countMatches(blocks: Block[], q: string): number {
  if (!q) return 0;
  const needle = q.toLowerCase();
  let total = 0;
  const countIn = (s: string) => {
    let n = 0;
    let from = 0;
    while (true) {
      const idx = s.toLowerCase().indexOf(needle, from);
      if (idx === -1) break;
      n += 1;
      from = idx + needle.length;
    }
    return n;
  };
  for (const b of blocks) {
    if (b.kind === "h" || b.kind === "p" || b.kind === "code" || b.kind === "quote") total += countIn(b.text);
    else if (b.kind === "ul" || b.kind === "ol") b.items.forEach((it) => (total += countIn(it)));
    else if (b.kind === "table") {
      b.headers.forEach((h) => (total += countIn(h)));
      b.rows.forEach((r) => r.forEach((c) => (total += countIn(c))));
    }
  }
  return total;
}

export default function TechnicalHelpPage() {
  const t = useT();
  const [data, setData] = useState<TechnicalArchitectureResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const announcedRef = useRef(false);

  useEffect(() => {
    if (!announcedRef.current) {
      announcedRef.current = true;
      logBus.emit({
        source: "frontend",
        level: "info",
        message: "technical-help page opened",
      });
    }
    const ctrl = new AbortController();
    getTechnicalArchitecture(ctrl.signal)
      .then((d) => setData(d))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    return () => ctrl.abort();
  }, []);

  const blocks = useMemo(() => (data ? parseMarkdown(data.markdown) : []), [data]);
  const filteredBlocks = useMemo(
    () => (query ? blocks.filter((b) => blockMatchesQuery(b, query)) : blocks),
    [blocks, query],
  );
  const headings = useMemo(
    () => blocks.filter((b): b is Extract<Block, { kind: "h" }> => b.kind === "h" && b.level <= 2),
    [blocks],
  );
  const matches = useMemo(() => countMatches(blocks, query), [blocks, query]);

  return (
    <div className={styles.page}>
      <h1>
        {t("technical.title")} <HelpHint slug="technical-help" />
      </h1>
      <p className="muted">{t("technical.subtitle")}</p>

      {error && <div className={styles.error}>{t("technical.failedToLoad")}: {error}</div>}
      {!data && !error && <div className={styles.loading}>{t("technical.loading")}</div>}

      {data && (
        <>
          <div className={styles.toolbar}>
            <input
              type="search"
              className={styles.search}
              placeholder={t("technical.searchPlaceholder")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="technical-search"
            />
            {query && (
              <span className={styles.matchCount}>
                {t("technical.matchCount").replace("{n}", String(matches))}
              </span>
            )}
            <a
              className={styles.downloadLink}
              href={getTechnicalArchitectureMarkdownUrl()}
              target="_blank"
              rel="noreferrer"
            >
              {t("technical.downloadMarkdown")}
            </a>
          </div>

          <div className={styles.meta}>
            <div>
              <strong>{t("technical.sourcePath")}:</strong> <code>{data.source_path}</code>
            </div>
            <div>
              <strong>{t("technical.generatedAt")}:</strong>{" "}
              {new Date(data.generated_at).toLocaleString()}
            </div>
          </div>

          <div className={styles.body}>
            {!query && headings.length > 0 && (
              <aside className={styles.toc}>
                <h3>{t("technical.tocTitle")}</h3>
                <ul>
                  {headings.map((h) => (
                    <li key={h.anchor} className={`tocL${h.level}`}>
                      <a href={`#${h.anchor}`}>{h.text}</a>
                    </li>
                  ))}
                </ul>
              </aside>
            )}

            <article className={styles.article}>
              {filteredBlocks.length === 0 && (
                <p className={styles.noResults}>{t("technical.noResults")}</p>
              )}
              {filteredBlocks.map((block, idx) => {
                if (block.kind === "h") {
                  const Tag = (`h${block.level}` as unknown) as keyof JSX.IntrinsicElements;
                  return (
                    <Tag key={idx} id={block.anchor} className={styles[`h${block.level}`]}>
                      {renderInline(block.text, query)}
                    </Tag>
                  );
                }
                if (block.kind === "p") {
                  return <p key={idx}>{renderInline(block.text, query)}</p>;
                }
                if (block.kind === "ul") {
                  return (
                    <ul key={idx}>
                      {block.items.map((item, j) => (
                        <li key={j}>{renderInline(item, query)}</li>
                      ))}
                    </ul>
                  );
                }
                if (block.kind === "ol") {
                  return (
                    <ol key={idx}>
                      {block.items.map((item, j) => (
                        <li key={j}>{renderInline(item, query)}</li>
                      ))}
                    </ol>
                  );
                }
                if (block.kind === "code") {
                  return (
                    <pre key={idx} className={styles.code}>
                      <code>{block.text}</code>
                    </pre>
                  );
                }
                if (block.kind === "quote") {
                  return (
                    <blockquote key={idx} className={styles.quote}>
                      {renderInline(block.text, query)}
                    </blockquote>
                  );
                }
                if (block.kind === "table") {
                  return (
                    <div key={idx} className={styles.tableWrap}>
                      <table>
                        <thead>
                          <tr>
                            {block.headers.map((h, j) => (
                              <th key={j}>{renderInline(h, query)}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {block.rows.map((row, ri) => (
                            <tr key={ri}>
                              {row.map((cell, ci) => (
                                <td key={ci}>{renderInline(cell, query)}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  );
                }
                return <hr key={idx} />;
              })}
            </article>
          </div>
        </>
      )}
    </div>
  );
}
