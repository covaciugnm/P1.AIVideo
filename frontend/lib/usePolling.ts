"use client";

import { useEffect, useRef, useState } from "react";

interface UsePollingOptions {
  readonly intervalMs: number;
  readonly enabled?: boolean;
}

interface UsePollingResult<T> {
  readonly data: T | null;
  readonly error: Error | null;
  readonly loading: boolean;
  readonly refetch: () => Promise<void>;
}

export function usePolling<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  options: UsePollingOptions,
): UsePollingResult<T> {
  const { intervalMs, enabled = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const runRef = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const run = async (): Promise<void> => {
      try {
        const result = await loaderRef.current(controller.signal);
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled && !(err instanceof DOMException && err.name === "AbortError")) {
          setError(err instanceof Error ? err : new Error(String(err)));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          timer = setTimeout(run, intervalMs);
        }
      }
    };

    runRef.current = run;
    void run();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer !== null) clearTimeout(timer);
      runRef.current = null;
    };
  }, [enabled, intervalMs]);

  const refetch = async (): Promise<void> => {
    if (runRef.current) await runRef.current();
  };

  return { data, error, loading, refetch };
}
