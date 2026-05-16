// Help content data model. Plain TS — no markdown dependency, no
// runtime parsing. Authors write structured blocks; the renderer maps
// each block type to a React element. Keeps the bundle small and gives
// us search + deep linking for free.

export type HelpBlock =
  | { readonly type: "p"; readonly text: string }
  | { readonly type: "h"; readonly level: 2 | 3 | 4; readonly text: string }
  | {
      readonly type: "code";
      readonly lang?: string;
      readonly text: string;
      readonly caption?: string;
    }
  | {
      readonly type: "list";
      readonly ordered?: boolean;
      readonly items: readonly (string | readonly string[])[];
    }
  | {
      readonly type: "kv";
      readonly caption?: string;
      readonly rows: readonly (readonly [string, string])[];
    }
  | {
      readonly type: "callout";
      readonly tone: "info" | "warn" | "danger" | "success";
      readonly title?: string;
      readonly text: string;
    }
  | { readonly type: "link"; readonly href: string; readonly text: string }
  | { readonly type: "linkArticle"; readonly slug: string; readonly label?: string }
  | { readonly type: "spacer" };

export interface HelpArticle {
  readonly slug: string;
  readonly title: string;
  readonly section: string;
  readonly summary: string;
  readonly keywords: readonly string[];
  readonly body: readonly HelpBlock[];
  readonly related?: readonly string[];
  readonly updated?: string;
}

export interface HelpSection {
  readonly id: string;
  readonly title: string;
  readonly description?: string;
  readonly order: number;
}
