// Phase 11A — Help corpus selector. ``getLocalizedHelpCorpus(lang)``
// returns the right ``HelpTopic`` map for the active UI language. The
// HelpOverlay uses this; tests import the per-language files directly.

import type { LanguageCode } from "@/lib/i18n/types";

import { HELP_TOPICS_EN, type HelpTopic } from "./en";
import { HELP_TOPICS_RO } from "./ro";

const CORPORA: Readonly<Record<LanguageCode, Readonly<Record<string, HelpTopic>>>> = {
  en: HELP_TOPICS_EN,
  ro: HELP_TOPICS_RO,
};

export function getLocalizedHelpCorpus(
  lang: LanguageCode | string,
): Readonly<Record<string, HelpTopic>> {
  if (lang === "ro") return HELP_TOPICS_RO;
  if (lang === "en") return HELP_TOPICS_EN;
  return HELP_TOPICS_EN;
}

export function getHelpTopic(
  lang: LanguageCode | string,
  id: string,
): HelpTopic | undefined {
  const corpus = getLocalizedHelpCorpus(lang);
  return corpus[id] ?? HELP_TOPICS_EN[id]; // fallback to EN if RO is missing
}

export function listHelpTopicIds(
  lang: LanguageCode | string,
): readonly string[] {
  return Object.keys(getLocalizedHelpCorpus(lang));
}

export type { HelpTopic } from "./en";
export { CORPORA };
