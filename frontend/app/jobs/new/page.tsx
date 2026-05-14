"use client";

import { useEffect, useState } from "react";

import { CreateJobForm } from "@/components/CreateJobForm";
import { ErrorMessage } from "@/components/ErrorMessage";
import { LoadingState } from "@/components/LoadingState";
import { getUiOptions } from "@/lib/api";
import type { UIOptions } from "@/lib/types";

export default function NewJobPage() {
  const [uiOptions, setUiOptions] = useState<UIOptions | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const opts = await getUiOptions(controller.signal);
        setUiOptions(opts);
      } catch (err) {
        if (!(err instanceof DOMException && err.name === "AbortError")) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    })();
    return () => controller.abort();
  }, []);

  return (
    <div>
      <h1>Create a new job</h1>
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
