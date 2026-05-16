"use client";

import { artifactContentUrl } from "@/lib/api";
import {
  formatBytes,
  formatDurationSec,
  shortHash,
  shortId,
} from "@/lib/format";
import type { ArtifactResponse } from "@/lib/types";

import styles from "./VideoArtifactPreview.module.css";

interface VideoArtifactPreviewProps {
  readonly artifacts: readonly ArtifactResponse[];
}

export function VideoArtifactPreview({ artifacts }: VideoArtifactPreviewProps) {
  // Phase 8A: ``video`` artifacts.
  // Phase 8B: ``final_export`` artifacts when they carry the real MP4
  // variant (mime_type=video/mp4). The publisher's JSON manifest has
  // ``mime_type=application/json`` so it's correctly excluded.
  const videos = artifacts.filter(
    (a) =>
      a.artifact_type === "video" ||
      (a.artifact_type === "final_export" && a.mime_type === "video/mp4"),
  );
  if (videos.length === 0) return null;
  return (
    <section className="card">
      <h2>Video preview ({videos.length})</h2>
      <ul className={styles.list}>
        {videos.map((a) => (
          <li key={a.artifact_id} className={styles.item}>
            <VideoPreviewItem artifact={a} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function VideoPreviewItem({ artifact }: { readonly artifact: ArtifactResponse }) {
  const src = artifactContentUrl(artifact.artifact_id);
  const dl = artifactContentUrl(artifact.artifact_id, { download: true });
  const provider =
    (artifact.metadata_summary?.["provider_id"] as string | undefined) ??
    (artifact.metadata_summary?.["sadtalker_details"] !== undefined
      ? "sadtalker"
      : undefined);
  const isFinalExport = artifact.artifact_type === "final_export";
  const watermark =
    (artifact.metadata_summary?.["watermark_status"] as string | undefined) ??
    null;
  const c2pa =
    (artifact.metadata_summary?.["c2pa_status"] as string | undefined) ?? null;
  const dims =
    artifact.width !== null && artifact.height !== null
      ? `${artifact.width}×${artifact.height}`
      : null;
  return (
    <>
      <div className={styles.meta}>
        <code className={styles.id}>{shortId(artifact.artifact_id)}</code>
        <span className={styles.mime}>{artifact.mime_type ?? "video/?"}</span>
        {provider && <span className={styles.badge}>{provider}</span>}
        {isFinalExport && <span className={styles.badgeFinal}>final export</span>}
        {watermark && watermark !== "applied" && (
          <span className={styles.badgePending}>watermark {watermark}</span>
        )}
        {c2pa && c2pa !== "signed" && (
          <span className={styles.badgePending}>c2pa {c2pa}</span>
        )}
      </div>
      <video
        className={styles.player}
        controls
        preload="metadata"
        src={src}
      >
        <p className={styles.fallback}>
          Your browser cannot play this video. Use{" "}
          <a href={dl} download>
            Download
          </a>{" "}
          to fetch the MP4 file instead.
        </p>
      </video>
      <dl className={styles.metaList}>
        <div>
          <dt>Size</dt>
          <dd>{formatBytes(artifact.size_bytes)}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>
            {artifact.duration_seconds !== null
              ? formatDurationSec(artifact.duration_seconds)
              : "—"}
          </dd>
        </div>
        <div>
          <dt>Dimensions</dt>
          <dd>{dims ?? "—"}</dd>
        </div>
        <div>
          <dt>SHA-256</dt>
          <dd title={artifact.checksum_sha256 ?? ""}>
            <code>{shortHash(artifact.checksum_sha256)}</code>
          </dd>
        </div>
      </dl>
      <div className={styles.actions}>
        <a className={styles.downloadBtn} href={dl} download>
          Download MP4
        </a>
      </div>
    </>
  );
}
