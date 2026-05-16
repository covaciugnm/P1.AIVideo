"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { getActiveApiBaseUrl } from "@/lib/settings";

import { DICTIONARY_EN } from "./dictionaries/en";
import { DICTIONARY_RO } from "./dictionaries/ro";
import {
  DEFAULT_LANGUAGE,
  LANGUAGE_META,
  SUPPORTED_LANGUAGE_CODES,
  type Dictionary,
  type LanguageCode,
} from "./types";

const STORAGE_KEY = "aivideo:ui-language";

const DICTIONARIES: Readonly<Record<LanguageCode, Dictionary>> = {
  ro: DICTIONARY_RO,
  en: DICTIONARY_EN,
};

export type TParams = Readonly<Record<string, string | number>>;

export interface LanguageContextValue {
  readonly language: LanguageCode;
  readonly setLanguage: (code: LanguageCode) => void;
  readonly t: (path: string, params?: TParams) => string;
  readonly dict: Dictionary;
  /** True once we've read the persisted backend setting at least once. */
  readonly hydrated: boolean;
}

const LangCtx = createContext<LanguageContextValue | null>(null);

function readLocalStorage(): LanguageCode | null {
  if (typeof window === "undefined") return null;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v && (SUPPORTED_LANGUAGE_CODES as readonly string[]).includes(v)) {
      return v as LanguageCode;
    }
  } catch {
    /* private mode */
  }
  return null;
}

function writeLocalStorage(code: LanguageCode): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* private mode */
  }
}

/** Walks ``"a.b.c"`` paths through the dictionary. Falls back to English
 * if missing in the selected language, then to the raw key. */
function lookup(dict: Dictionary, fallback: Dictionary, path: string): string {
  const parts = path.split(".");
  // Selected language first.
  let cur: unknown = dict;
  for (const part of parts) {
    if (cur && typeof cur === "object" && part in (cur as object)) {
      cur = (cur as Record<string, unknown>)[part];
    } else {
      cur = undefined;
      break;
    }
  }
  if (typeof cur === "string") return cur;
  // Fallback to English.
  cur = fallback;
  for (const part of parts) {
    if (cur && typeof cur === "object" && part in (cur as object)) {
      cur = (cur as Record<string, unknown>)[part];
    } else {
      cur = undefined;
      break;
    }
  }
  if (typeof cur === "string") return cur;
  return path;
}

/** Replace ``{name}`` placeholders with values from ``params``. Unknown
 * placeholders are left untouched so an underspecified call still
 * produces a readable string the operator can flag. */
function interpolate(template: string, params?: TParams): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (whole, key: string) => {
    const v = params[key];
    if (v === undefined || v === null) return whole;
    return String(v);
  });
}

export function LanguageProvider({ children }: { readonly children: ReactNode }) {
  const [language, setLanguageState] = useState<LanguageCode>(DEFAULT_LANGUAGE);
  const [hydrated, setHydrated] = useState(false);
  const hydratedRef = useRef(false);

  // First read: localStorage (instant), then backend (authoritative).
  useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;
    const cached = readLocalStorage();
    if (cached) setLanguageState(cached);
    // Don't block the UI on the backend round-trip; mark hydrated as soon
    // as we've checked localStorage so SSR-style flickers don't happen.
    setHydrated(true);
    const url = `${getActiveApiBaseUrl()}/api/v1/settings/ui`;
    fetch(url, { method: "GET", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((body: { ui_language?: string } | null) => {
        const lang = body?.ui_language;
        if (lang && (SUPPORTED_LANGUAGE_CODES as readonly string[]).includes(lang)) {
          // Backend wins on first hydrate so a different browser sees
          // the same operator-wide setting.
          setLanguageState(lang as LanguageCode);
          writeLocalStorage(lang as LanguageCode);
        }
      })
      .catch(() => {
        /* offline — localStorage already applied */
      });
  }, []);

  const setLanguage = useCallback((code: LanguageCode) => {
    setLanguageState(code);
    writeLocalStorage(code);
    // Best-effort PATCH to backend so the next session (or another
    // browser) sees the same operator-wide preference.
    try {
      const url = `${getActiveApiBaseUrl()}/api/v1/settings/ui`;
      void fetch(url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ui_language: code }),
      });
    } catch {
      /* swallow — localStorage already covers the fast path */
    }
  }, []);

  const dict = DICTIONARIES[language];
  const enDict = DICTIONARIES.en;

  const t = useCallback(
    (path: string, params?: TParams) =>
      interpolate(lookup(dict, enDict, path), params),
    [dict, enDict]
  );

  const value = useMemo<LanguageContextValue>(
    () => ({ language, setLanguage, t, dict, hydrated }),
    [language, setLanguage, t, dict, hydrated]
  );

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = language;
      document.documentElement.dir = LANGUAGE_META[language].rtl ? "rtl" : "ltr";
    }
  }, [language]);

  return <LangCtx.Provider value={value}>{children}</LangCtx.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LangCtx);
  if (!ctx) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return ctx;
}

export function useT(): (path: string, params?: TParams) => string {
  return useLanguage().t;
}
