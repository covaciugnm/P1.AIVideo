// Simple, zero-dep token scorer for help articles. Good enough at this
// content size that adding a search library would be over-engineering.

import { HELP_ARTICLES } from "./content";
import type { HelpArticle, HelpBlock } from "./types";

export interface HelpSearchHit {
  readonly article: HelpArticle;
  readonly score: number;
  readonly matchedIn: readonly ("title" | "summary" | "keyword" | "body" | "section")[];
}

const TITLE_WEIGHT = 8;
const SUMMARY_WEIGHT = 5;
const KEYWORD_WEIGHT = 4;
const SECTION_WEIGHT = 2;
const BODY_WEIGHT = 1;

function blockText(block: HelpBlock): string {
  switch (block.type) {
    case "p":
    case "h":
      return block.text;
    case "code":
      return `${block.caption ?? ""} ${block.text}`;
    case "list":
      return block.items
        .map((it) => (Array.isArray(it) ? it.join(" ") : (it as string)))
        .join(" ");
    case "kv":
      return [
        block.caption ?? "",
        ...block.rows.map(([k, v]) => `${k} ${v}`),
      ].join(" ");
    case "callout":
      return `${block.title ?? ""} ${block.text}`;
    case "link":
      return `${block.text} ${block.href}`;
    case "linkArticle":
      return block.label ?? "";
    case "spacer":
      return "";
  }
}

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s.-]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
}

function countOccurrences(haystackTokens: string[], needle: string): number {
  let n = 0;
  for (const t of haystackTokens) {
    if (t === needle) n += 2;
    else if (t.includes(needle)) n += 1;
  }
  return n;
}

export function searchHelp(query: string, limit = 12): readonly HelpSearchHit[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const needles = tokenize(q);
  if (needles.length === 0) return [];

  const hits: HelpSearchHit[] = [];
  for (const article of HELP_ARTICLES) {
    const titleTokens = tokenize(article.title);
    const summaryTokens = tokenize(article.summary);
    const sectionTokens = tokenize(article.section);
    const keywordTokens = article.keywords.flatMap((k) => tokenize(k));
    const bodyTokens = tokenize(article.body.map(blockText).join(" "));

    let score = 0;
    const matchedIn = new Set<HelpSearchHit["matchedIn"][number]>();
    for (const needle of needles) {
      const inTitle = countOccurrences(titleTokens, needle);
      const inSummary = countOccurrences(summaryTokens, needle);
      const inKeyword = countOccurrences(keywordTokens, needle);
      const inSection = countOccurrences(sectionTokens, needle);
      const inBody = countOccurrences(bodyTokens, needle);

      if (inTitle) matchedIn.add("title");
      if (inSummary) matchedIn.add("summary");
      if (inKeyword) matchedIn.add("keyword");
      if (inSection) matchedIn.add("section");
      if (inBody) matchedIn.add("body");

      score +=
        inTitle * TITLE_WEIGHT +
        inSummary * SUMMARY_WEIGHT +
        inKeyword * KEYWORD_WEIGHT +
        inSection * SECTION_WEIGHT +
        inBody * BODY_WEIGHT;
    }
    if (score > 0) {
      hits.push({ article, score, matchedIn: [...matchedIn] });
    }
  }
  hits.sort((a, b) => b.score - a.score);
  return hits.slice(0, limit);
}
