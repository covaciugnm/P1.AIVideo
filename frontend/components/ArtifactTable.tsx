"use client";

import {
  formatBytes,
  formatDate,
  formatDurationSec,
  humanize,
  shortHash,
  shortId,
} from "@/lib/format";
import { useT } from "@/lib/i18n/LanguageContext";
import type { ArtifactResponse } from "@/lib/types";

import styles from "./ArtifactTable.module.css";

interface ArtifactTableProps {
  readonly artifacts: readonly ArtifactResponse[];
}

export function ArtifactTable({ artifacts }: ArtifactTableProps) {
  const t = useT();
  if (artifacts.length === 0) {
    return <p className={styles.empty}>{t("artifactTable.empty")}</p>;
  }
  return (
    <div className={styles.scroll}>
      <table className="simple">
        <thead>
          <tr>
            <th>{t("artifactTable.header_type")}</th>
            <th>{t("artifactTable.header_id")}</th>
            <th>{t("artifactTable.header_mime")}</th>
            <th>{t("artifactTable.header_size")}</th>
            <th>{t("artifactTable.header_dim")}</th>
            <th>{t("artifactTable.header_sha")}</th>
            <th>{t("artifactTable.header_real")}</th>
            <th>{t("artifactTable.header_created")}</th>
          </tr>
        </thead>
        <tbody>
          {artifacts.map((a) => (
            <tr key={a.artifact_id}>
              <td>{humanize(a.artifact_type)}</td>
              <td>
                <code>{shortId(a.artifact_id)}</code>
              </td>
              <td>{a.mime_type ?? "—"}</td>
              <td>{formatBytes(a.size_bytes)}</td>
              <td>{describeShape(a)}</td>
              <td>
                <code title={a.checksum_sha256 ?? ""}>
                  {shortHash(a.checksum_sha256)}
                </code>
              </td>
              <td title={a.uri}>{describeRealness(a, t)}</td>
              <td>{formatDate(a.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function describeShape(a: ArtifactResponse): string {
  if (a.width !== null && a.height !== null) return `${a.width}×${a.height}`;
  if (a.duration_seconds !== null) {
    const rate =
      a.sample_rate !== null && a.channels !== null
        ? ` · ${a.sample_rate} Hz · ${a.channels}ch`
        : "";
    return `${formatDurationSec(a.duration_seconds)}${rate}`;
  }
  return "—";
}

function describeRealness(
  a: ArtifactResponse,
  t: (key: string) => string,
): string {
  if (a.uri.startsWith("placeholder://")) return t("artifactTable.real_metadata");
  if (a.local_path && a.checksum_sha256) return t("artifactTable.real_yes");
  if (a.checksum_sha256 && (a.mime_type ?? "").startsWith("application/json")) {
    return t("artifactTable.real_manifest");
  }
  return t("artifactTable.real_no");
}
