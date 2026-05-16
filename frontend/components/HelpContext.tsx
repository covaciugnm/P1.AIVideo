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

import { HELP_DEFAULT_SLUG, getArticleBySlug } from "@/lib/help/content";

interface HelpState {
  readonly open: boolean;
  readonly slug: string;
  readonly history: readonly string[];      // back-stack
  readonly future: readonly string[];       // forward-stack
}

interface HelpContextValue {
  readonly open: boolean;
  readonly slug: string;
  readonly canGoBack: boolean;
  readonly canGoForward: boolean;
  openHelp: (slug?: string) => void;
  closeHelp: () => void;
  navigate: (slug: string) => void;
  back: () => void;
  forward: () => void;
  toggle: () => void;
}

const DEFAULT_STATE: HelpState = {
  open: false,
  slug: HELP_DEFAULT_SLUG,
  history: [],
  future: [],
};

const HelpCtx = createContext<HelpContextValue | null>(null);

const STORAGE_KEY = "aivideo:help:last-slug";
const HASH_PREFIX = "#help/";

function readHash(): string | null {
  if (typeof window === "undefined") return null;
  const h = window.location.hash;
  if (h.startsWith(HASH_PREFIX)) {
    const slug = h.slice(HASH_PREFIX.length);
    return slug && getArticleBySlug(slug) ? slug : null;
  }
  return null;
}

function writeHash(slug: string | null) {
  if (typeof window === "undefined") return;
  const target = slug ? `${HASH_PREFIX}${slug}` : "";
  // Avoid scroll jumps when changing the hash.
  const { pathname, search } = window.location;
  history.replaceState(null, "", `${pathname}${search}${target}`);
}

export function HelpProvider({ children }: { readonly children: ReactNode }) {
  const [state, setState] = useState<HelpState>(DEFAULT_STATE);
  const hydratedRef = useRef(false);

  // Hydrate from URL hash (preferred) or localStorage on first mount.
  useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;
    const hashSlug = readHash();
    if (hashSlug) {
      setState({ open: true, slug: hashSlug, history: [], future: [] });
      return;
    }
    try {
      const last = window.localStorage.getItem(STORAGE_KEY);
      if (last && getArticleBySlug(last)) {
        setState((s) => ({ ...s, slug: last }));
      }
    } catch {
      // ignore — private mode, etc.
    }
  }, []);

  // Persist + sync the hash whenever we open/close/navigate.
  useEffect(() => {
    if (!hydratedRef.current) return;
    if (state.open) {
      writeHash(state.slug);
      try {
        window.localStorage.setItem(STORAGE_KEY, state.slug);
      } catch {
        // ignore
      }
    } else if (window.location.hash.startsWith(HASH_PREFIX)) {
      writeHash(null);
    }
  }, [state.open, state.slug]);

  const openHelp = useCallback((slug?: string) => {
    setState((prev) => {
      const target = slug && getArticleBySlug(slug) ? slug : prev.slug;
      return {
        ...prev,
        open: true,
        slug: target,
        // Reset forward stack when opening freshly.
        future: slug ? [] : prev.future,
      };
    });
  }, []);

  const closeHelp = useCallback(() => {
    setState((prev) => ({ ...prev, open: false }));
  }, []);

  const navigate = useCallback((slug: string) => {
    if (!getArticleBySlug(slug)) return;
    setState((prev) => {
      if (prev.slug === slug) return prev;
      return {
        ...prev,
        slug,
        history: [...prev.history, prev.slug],
        future: [],
      };
    });
  }, []);

  const back = useCallback(() => {
    setState((prev) => {
      if (prev.history.length === 0) return prev;
      const newHistory = prev.history.slice(0, -1);
      const previousSlug = prev.history[prev.history.length - 1];
      return {
        ...prev,
        slug: previousSlug,
        history: newHistory,
        future: [prev.slug, ...prev.future],
      };
    });
  }, []);

  const forward = useCallback(() => {
    setState((prev) => {
      if (prev.future.length === 0) return prev;
      const [nextSlug, ...rest] = prev.future;
      return {
        ...prev,
        slug: nextSlug,
        history: [...prev.history, prev.slug],
        future: rest,
      };
    });
  }, []);

  const toggle = useCallback(() => {
    setState((prev) => ({ ...prev, open: !prev.open }));
  }, []);

  // Global keyboard listener: `?` opens, `Esc` closes.
  useEffect(() => {
    const isTypingTarget = (target: EventTarget | null): boolean => {
      if (!(target instanceof HTMLElement)) return false;
      const tag = target.tagName.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return true;
      if (target.isContentEditable) return true;
      return false;
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && state.open) {
        e.preventDefault();
        closeHelp();
        return;
      }
      if (e.key === "?" && !isTypingTarget(e.target)) {
        e.preventDefault();
        if (state.open) closeHelp();
        else openHelp();
        return;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.open, openHelp, closeHelp]);

  const value = useMemo<HelpContextValue>(
    () => ({
      open: state.open,
      slug: state.slug,
      canGoBack: state.history.length > 0,
      canGoForward: state.future.length > 0,
      openHelp,
      closeHelp,
      navigate,
      back,
      forward,
      toggle,
    }),
    [state, openHelp, closeHelp, navigate, back, forward, toggle]
  );

  return <HelpCtx.Provider value={value}>{children}</HelpCtx.Provider>;
}

export function useHelp(): HelpContextValue {
  const ctx = useContext(HelpCtx);
  if (!ctx) {
    throw new Error("useHelp must be used within HelpProvider");
  }
  return ctx;
}
