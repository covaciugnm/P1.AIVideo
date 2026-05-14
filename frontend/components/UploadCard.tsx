"use client";

import { useRef, useState } from "react";

import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import type { UploadAudioResponse, UploadImageResponse } from "@/lib/types";

import { ErrorMessage } from "./ErrorMessage";
import styles from "./UploadCard.module.css";

type Kind = "audio" | "image";

interface UploadCardProps {
  readonly kind: Kind;
  readonly title: string;
  readonly help: string;
  readonly acceptExtensions: readonly string[];
  readonly maxBytes: number;
  readonly onUploaded: (
    result: UploadAudioResponse | UploadImageResponse,
  ) => void;
  readonly currentArtifactId?: string | null;
}

export function UploadCard({
  kind,
  title,
  help,
  acceptExtensions,
  maxBytes,
  onUploaded,
  currentArtifactId,
}: UploadCardProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<File | null>(null);

  const accept = acceptExtensions.join(",");

  const handleFiles = (files: FileList | null) => {
    setError(null);
    if (!files || files.length === 0) return;
    const file = files[0];
    if (!file) return;
    if (file.size > maxBytes) {
      setError(
        `File is ${formatBytes(file.size)}; max is ${formatBytes(maxBytes)}.`,
      );
      return;
    }
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!acceptExtensions.includes(ext)) {
      setError(
        `Unsupported extension ${ext}. Accepted: ${acceptExtensions.join(", ")}.`,
      );
      return;
    }
    setPending(file);
  };

  const handleUpload = async () => {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      const result =
        kind === "audio"
          ? await api.uploadAudio(pending)
          : await api.uploadImage(pending);
      onUploaded(result);
      setPending(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  const handleClear = () => {
    setPending(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <h3>{title}</h3>
        <span className={styles.help}>{help}</span>
      </div>
      <div className={styles.dropzone}>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          onChange={(e) => handleFiles(e.target.files)}
          disabled={busy}
        />
        {pending && (
          <div className={styles.pending}>
            <div>
              Selected: <code>{pending.name}</code> ({formatBytes(pending.size)})
            </div>
            <div className={styles.row}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleUpload}
                disabled={busy}
              >
                {busy ? "Uploading…" : "Upload"}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={handleClear}
                disabled={busy}
              >
                Clear
              </button>
            </div>
          </div>
        )}
        {!pending && currentArtifactId && (
          <p className={styles.muted}>
            Linked artifact: <code>{currentArtifactId.slice(0, 8)}</code>
          </p>
        )}
      </div>
      <p className={styles.note}>
        Max size: {formatBytes(maxBytes)}. Files are stored locally; nothing is
        sent to any third party.
      </p>
      {error && <ErrorMessage message={error} />}
    </div>
  );
}
