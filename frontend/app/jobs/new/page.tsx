"use client";

import { useEffect, useRef, useState } from "react";

import { CreateJobForm } from "@/components/CreateJobForm";
import { ErrorMessage } from "@/components/ErrorMessage";
import { HelpHint } from "@/components/HelpHint";
import { LoadingState } from "@/components/LoadingState";
import { getUiOptions } from "@/lib/api";
import * as logBus from "@/lib/log-bus";
import type { UIOptions } from "@/lib/types";

export default function NewJobPage() {
  const [uiOptions, setUiOptions] = useState<UIOptions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const announcedRef = useRef(false);

  useEffect(() => {
    if (!announcedRef.current) {
      announcedRef.current = true;
      logBus.emit({
        source: "frontend",
        level: "info",
        message: "create-job page opened",
      });
    }
    const controller = new AbortController();
    void (async () => {
      try {
        const opts = await getUiOptions(controller.signal);
        setUiOptions(opts);
      } catch (err) {
        if (!(err instanceof DOMException && err.name === "AbortError")) {
          const msg = err instanceof Error ? err.message : String(err);
          setError(msg);
          logBus.emit({
            source: "frontend",
            level: "error",
            message: "failed to load UI options",
            meta: { error: msg },
          });
        }
      }
    })();
    return () => controller.abort();
  }, []);

  return (
    <div>
      <h1>
        Create a new job
        <HelpHint slug="page-create-job" />
      </h1>
      <p className="muted">
        Submit a brief and choose a voice source. Compliance attestations are
        mandatory and load-bearing.
      </p>
      {error && <ErrorMessage message={error} title="Failed to load options" />}
      {!uiOptions && !error && <LoadingState label="Loading options…" />}
      {uiOptions && <CreateJobForm uiOptions={uiOptions} />}
    </div>
  );
}
