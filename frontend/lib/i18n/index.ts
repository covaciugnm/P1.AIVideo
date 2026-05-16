// Phase 11A — i18n public API.
//
// Operators read translations via ``useT()``/``useLanguage()``. Tests
// import the dictionaries directly via this entry point. New dictionaries
// go under ``./dictionaries/<code>.ts`` and get registered in
// ``DICTIONARIES`` below.

export { useT, useLanguage, LanguageProvider } from "./LanguageContext";
export type { Dictionary, LanguageCode, LanguageMeta } from "./types";
export {
  DEFAULT_LANGUAGE,
  LANGUAGE_META,
  SUPPORTED_LANGUAGE_CODES,
} from "./types";

import { DICTIONARY_EN } from "./dictionaries/en";
import { DICTIONARY_RO } from "./dictionaries/ro";
import type { Dictionary, LanguageCode } from "./types";

export const DICTIONARIES: Readonly<Record<LanguageCode, Dictionary>> = {
  en: DICTIONARY_EN,
  ro: DICTIONARY_RO,
};
