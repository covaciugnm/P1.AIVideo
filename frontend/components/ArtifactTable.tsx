import {
  formatBytes,
  formatDate,
  formatDurationSec,
  humanize,
  shortHash,
  shortId,
} from "@/lib/format";
import type { ArtifactResponse } from "@/lib/types";

import styles from "./ArtifactTable.module.css";

interface ArtifactTableProps {
  readonly artifacts: readonly ArtifactResponse[];
}

export function ArtifactTable({ artifacts }: ArtifactTableProps) {
  if (artifacts.length === 0) {
    return <p className={styles.empty}>No artifacts produced yet.</p>;
  }
  return (
    <div className={styles.scroll}>
      <table className="simple">
        <thead>
          <tr>
            <th>Type</th>
            <th>ID</th>
            <th>MIME</th>
            <th>Size</th>
            <th>Dim / Dur</th>
            <th>SHA-256</th>
            <th>Created</th>
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
