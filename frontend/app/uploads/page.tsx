"use client";

import { useEffect, useRef, useState } from "react";

import { ErrorMessage } from "@/components/ErrorMessage";
import { LoadingState } from "@/components/LoadingState";
import { UploadCard } from "@/components/UploadCard";
import { ApiError, getUiOptions, uploadText } from "@/lib/api";
import { formatBytes, formatDate, formatDurationSec, shortHash } from "@/lib/format";
import * as logBus from "@/lib/log-bus";
import type {
  UIOptions,
  UploadAudioResponse,
  UploadImageResponse,
  UploadTextResponse,
} from "@/lib/types";

import styles from "./page.module.css";

type Recent =
  | { kind: "text"; r: UploadTextResponse; createdAt: string }
  | { kind: "audio"; r: UploadAudioResponse; createdAt: string }
  | { kind: "image"; r: UploadImageResponse; createdAt: string };

export default function UploadsPage() {
  const [uiOptions, setUiOptions] = useState<UIOptions | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [recent, setRecent] = useState<Recent[]>([]);
  const announcedRef = useRef(false);

  useEffect(() => {
    if (!announcedRef.current) {
      announcedRef.current = true;
      logBus.emit({
        source: "frontend",
        level: "info",
        message: "uploads page opened",
      });
    }
    const controller = new AbortController();
    (async () => {
      try {
        const opts = await getUiOptions(controller.signal);
        setUiOptions(opts);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setLoadError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => controller.abort();
  }, []);

  const addRecent = (r: Recent) => setRecent((prev) => [r, ...prev].slice(0, 20));

  if (loadError) {
    return (
      <ErrorMessage message={loadError} title="Failed to load upload options" />
    );
  }
  if (!uiOptions) return <LoadingState label="Loading upload options…" />;

  return (
    <div>
      <h1>Uploads</h1>
      <p className="muted">
        Register text, audio, or image artifacts. Each upload is stored
        locally on the backend and returns an artifact id you can reference
        when creating a job.
      </p>

      <div className={styles.grid}>
        <section className="card">
          <h2>Text / script</h2>
          <UploadTextPanel
            maxChars={uiOptions.upload_limits.script_text_max_chars}
            onUploaded={(r) =>
              addRecent({ kind: "text", r, createdAt: new Date().toISOString() })
            }
          />
        </section>

        <section className="card">
          <h2>Audio (WAV)</h2>
          <UploadCard
            kind="audio"
            title="Provided audio"
            help="WAV file under the configured max size."
            acceptExtensions={uiOptions.upload_limits.accepted_audio_extensions}
            maxBytes={uiOptions.upload_limits.audio_max_bytes}
            onUploaded={(r) =>
              addRecent({
                kind: "audio",
                r: r as UploadAudioResponse,
                createdAt: new Date().toISOString(),
              })
            }
          />
        </section>

        <section className="card">
          <h2>Image (PNG / JPEG / WebP)</h2>
          <UploadCard
            kind="image"
            title="Portrait image"
            help="Synthetic-only portrait."
            acceptExtensions={uiOptions.upload_limits.accepted_image_extensions}
            maxBytes={uiOptions.upload_limits.image_max_bytes}
            onUploaded={(r) =>
              addRecent({
                kind: "image",
                r: r as UploadImageResponse,
                createdAt: new Date().toISOString(),
              })
            }
          />
        </section>
      </div>

      <section className="card">
        <h2>Recent uploads (this tab)</h2>
        {recent.length === 0 ? (
          <p className="muted">No uploads yet in this session.</p>
        ) : (
          <ul className={styles.recentList}>
            {recent.map((r, i) => (
              <RecentItem key={i} entry={r} />
            ))}
          </ul>
        )}
        <p className="muted">
          The list is local to this tab. Refreshing the page clears it.
          Backend persistence + a global artifacts endpoint land in a later
          phase.
        </p>
      </section>
    </div>
  );
}

function UploadTextPanel({
  maxChars,
  onUploaded,
}: {
  readonly maxChars: number;
  readonly onUploaded: (r: UploadTextResponse) => void;
}) {
  const [scriptText, setScriptText] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const body = scriptText.trim();
    if (body.length === 0) {
      setError("Script text cannot be empty.");
      return;
    }
    setBusy(true);
    setError(null);
    logBus.emit({
      source: "frontend",
      level: "info",
      message: `upload-text started (${body.length} chars)`,
      meta: { chars: body.length, has_title: title.length > 0 },
    });
    try {
      const r = await uploadText({
        script_text: body,
        title: title.trim() || null,
      });
      logBus.emit({
        source: "frontend",
        level: "success",
        message: `upload-text succeeded → ${r.artifact_id}`,
        meta: { artifact_id: r.artifact_id },
      });
      onUploaded(r);
      setScriptText("");
      setTitle("");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      setError(msg);
      logBus.emit({
        source: "frontend",
        level: "error",
        message: "upload-text failed",
        meta: { error: msg },
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="field">
        <label htmlFor="upload-title">Title (optional)</label>
        <input
          id="upload-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
        />
      </div>
      <div className="field">
        <label htmlFor="upload-script">Script text</label>
        <textarea
          id="upload-script"
          value={scriptText}
          onChange={(e) => setScriptText(e.target.value)}
          maxLength={maxChars}
        />
        <span className={styles.muted}>
          {scriptText.length} / {maxChars}
        </span>
      </div>
      {error && <ErrorMessage message={error} />}
      <button
        type="button"
        className="btn btn-primary"
        onClick={submit}
        disabled={busy}
      >
        {busy ? "Registering…" : "Register text"}
      </button>
    </div>
  );
}

function RecentItem({ entry }: { readonly entry: Recent }) {
  const id = entryArtifactId(entry);
  const meta = entryMetaSummary(entry);
  return (
    <li className={styles.recentItem}>
      <div className={styles.recentHeader}>
        <span className={styles.recentKind}>{entry.kind}</span>
        <span className={styles.recentTime}>{formatDate(entry.createdAt)}</span>
      </div>
      <div className={styles.recentRow}>
        <code className={styles.recentId}>{id}</code>
        <CopyButton text={id} label="Copy id" />
      </div>
      {meta && <div className={styles.recentMeta}>{meta}</div>}
    </li>
  );
}

function entryArtifactId(entry: Recent): string {
  if (entry.kind === "text") return entry.r.artifact_id;
  if (entry.kind === "audio") return entry.r.artifact_id;
  return entry.r.artifact_id;
}

function entryMetaSummary(entry: Recent): string | null {
  if (entry.kind === "audio") {
    const r = entry.r;
    return `${formatBytes(r.size_bytes)} · ${r.sample_rate} Hz · ${r.channels}ch · ${formatDurationSec(r.duration_seconds)} · sha256 ${shortHash(r.checksum_sha256)}`;
  }
  if (entry.kind === "image") {
    const r = entry.r;
    return `${r.width}×${r.height} · ${r.mime_type} · ${formatBytes(r.size_bytes)} · sha256 ${shortHash(r.checksum_sha256)}`;
  }
  // text
  const r = entry.r;
  return `${r.mime_type ?? "application/json"} · ${formatBytes(r.size_bytes ?? 0)} · sha256 ${shortHash(r.checksum_sha256)}`;
}

function CopyButton({ text, label }: { readonly text: string; readonly label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className={styles.copyBtn}
      onClick={() => {
        if (typeof navigator !== "undefined" && navigator.clipboard) {
          void navigator.clipboard.writeText(text).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          });
        }
      }}
    >
      {copied ? "Copied" : label}
    </button>
  );
}
