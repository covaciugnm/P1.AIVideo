export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diff = Date.now() - d.getTime();
  const sec = Math.round(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || bytes < 0) return "—";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exp = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const v = bytes / 1024 ** exp;
  return `${v.toFixed(v >= 10 || exp === 0 ? 0 : 1)} ${units[exp]}`;
}

export function formatDurationMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(2)} s`;
  const m = Math.floor(sec / 60);
  const s = (sec - m * 60).toFixed(0);
  return `${m}m ${s.padStart(2, "0")}s`;
}

export function formatDurationSec(sec: number | null | undefined): string {
  if (sec === null || sec === undefined) return "—";
  if (sec < 60) return `${sec.toFixed(2)} s`;
  const m = Math.floor(sec / 60);
  const s = (sec - m * 60).toFixed(1);
  return `${m}m ${s}s`;
}

export function shortHash(value: string | null | undefined): string {
  if (!value) return "—";
  if (value.length <= 12) return value;
  return `${value.slice(0, 8)}…${value.slice(-4)}`;
}

export function shortId(value: string | null | undefined): string {
  if (!value) return "—";
  if (value.length <= 8) return value;
  return value.slice(0, 8);
}

export function humanize(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

export function isTerminalStatus(status: string): boolean {
  return (
    status === "published" ||
    status === "rejected" ||
    status === "failed"
  );
}
