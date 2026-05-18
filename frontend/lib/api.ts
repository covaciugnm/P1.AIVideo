// Typed API client.
//
// One function per endpoint. Every backend route the UI consumes is
// declared here so that pages/components don't sprinkle raw `fetch`
// calls across the codebase.
//
// Phase 4D: the base URL is resolved on every request via
// ``getActiveApiBaseUrl()`` so the operator can override
// NEXT_PUBLIC_API_BASE_URL at runtime from the Settings tab without a
// rebuild. Every call also emits a structured log entry on the log-bus
// so the right sidebar can render an operator-visible activity stream.

import * as logBus from "./log-bus";
import { getActiveApiBaseUrl } from "./settings";
import type {
  ArtifactResponse,
  ArtifactTypeInfo,
  AudioFitCheckRequest,
  AudioFitCheckResponse,
  ComplianceEventResponse,
  CreateJobBody,
  CreateJobFromInputsBody,
  FinalExportResponse,
  FinalizeExportRequest,
  FinalizeExportResponse,
  JobDetail,
  JobFullSummary,
  JobProgress,
  JobResponse,
  JobStatus,
  JobSummary,
  JobUpdateBody,
  ProviderInfo,
  ProvidersResponse,
  QcInspectRequest,
  QcInspectResponse,
  QCReportResponse,
  ScriptGenerateError,
  ScriptGenerateRequest,
  ScriptGenerateResponse,
  StageInfo,
  StageTimelineEntry,
  SystemStatus,
  TTSGenerateError,
  TTSGenerateRequest,
  TTSGenerateResponse,
  UIOptions,
  UploadAudioResponse,
  UploadImageResponse,
  UploadTextResponse,
  VideoGenerateRequest,
  VideoGenerateResponse,
} from "./types";

export { getActiveApiBaseUrl };

export class ApiError extends Error {
  public readonly status: number;
  public readonly detail: string;

  constructor(status: number, detail: string) {
    super(`HTTP ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}


/**
 * Phase 8E — turn a FastAPI / Pydantic validation error blob into a
 * human-readable sentence the operator can act on.
 *
 * Input shapes we handle:
 *   1. Plain string (already human-readable).
 *   2. ``{"detail": "..."}``
 *   3. ``{"detail": [{"type": "...", "loc": [...], "msg": "...", "input": ...}]}``
 *      — the canonical Pydantic v2 shape.
 *   4. Anything else → ``JSON.stringify`` (last resort, so the operator
 *      sees *something*).
 */
export function humanizeApiDetail(raw: unknown): string {
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw);
      return humanizeApiDetail(parsed);
    } catch {
      return raw;
    }
  }
  if (raw && typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    const detail = obj["detail"];
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const lines: string[] = [];
      for (const item of detail) {
        if (item && typeof item === "object") {
          const it = item as Record<string, unknown>;
          const loc = Array.isArray(it["loc"])
            ? (it["loc"] as unknown[]).map(String).join(".")
            : "";
          const msg = typeof it["msg"] === "string" ? (it["msg"] as string) : "";
          const type = typeof it["type"] === "string" ? (it["type"] as string) : "";
          lines.push(
            type === "extra_forbidden"
              ? `Field "${loc}" is not accepted by this endpoint (backend/frontend contract mismatch).`
              : msg
                ? `${loc ? `${loc}: ` : ""}${msg}`
                : `Validation error at ${loc || "?"}.`,
          );
        }
      }
      if (lines.length > 0) return lines.join("; ");
    }
  }
  try {
    return JSON.stringify(raw);
  } catch {
    return String(raw);
  }
}

interface RequestOptions {
  readonly method?: "GET" | "POST" | "PATCH" | "DELETE";
  readonly body?: BodyInit | null;
  readonly headers?: Record<string, string>;
  readonly signal?: AbortSignal;
  readonly logLabel?: string;
}

function buildTimeApiBaseUrl(): string {
  return (
    (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) ||
    "http://localhost:8000"
  );
}

function urlSourceLabel(activeUrl: string): "user-override" | "build-time" {
  return activeUrl === buildTimeApiBaseUrl() ? "build-time" : "user-override";
}

function now(): number {
  if (typeof performance !== "undefined") return performance.now();
  return Date.now();
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const baseUrl = getActiveApiBaseUrl();
  const url = `${baseUrl}${path}`;
  const init: RequestInit = {
    method,
    headers: opts.headers,
    signal: opts.signal,
    cache: "no-store",
  };
  if (opts.body !== undefined && opts.body !== null) {
    init.body = opts.body;
  }
  const started = now();
  const logPath = opts.logLabel ?? path;
  try {
    const response = await fetch(url, init);
    const durationMs = Math.round(now() - started);
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const payload = (await response.json()) as { detail?: unknown };
        if (typeof payload.detail === "string") {
          detail = payload.detail;
        } else if (payload.detail !== undefined) {
          detail = JSON.stringify(payload.detail);
        }
      } catch {
        // body wasn't JSON; keep statusText
      }
      logBus.emit({
        source: "api",
        level: "error",
        message: `${method} ${logPath} → ${response.status}`,
        meta: {
          url,
          status: response.status,
          duration_ms: durationMs,
          detail,
          url_source: urlSourceLabel(baseUrl),
        },
      });
      throw new ApiError(response.status, detail);
    }
    logBus.emit({
      source: "api",
      level: response.status >= 400 ? "warning" : "info",
      message: `${method} ${logPath} → ${response.status}`,
      meta: {
        url,
        status: response.status,
        duration_ms: durationMs,
        url_source: urlSourceLabel(baseUrl),
      },
    });
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw err;
    }
    const durationMs = Math.round(now() - started);
    const errName = err instanceof Error ? err.name : "Error";
    const errMessage = err instanceof Error ? err.message : String(err);
    const hint =
      errMessage === "Failed to fetch"
        ? "network or CORS — check Settings → Backend API Base URL and backend CORS allow-list"
        : undefined;
    logBus.emit({
      source: "api",
      level: "error",
      message: `${method} ${logPath} → ${errName}: ${errMessage}`,
      meta: {
        url,
        duration_ms: durationMs,
        error_name: errName,
        error_message: errMessage,
        url_source: urlSourceLabel(baseUrl),
        ...(hint ? { hint } : {}),
      },
    });
    throw err;
  }
}

function jsonHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

// ---------------------------------------------------------------------------
// System + config
// ---------------------------------------------------------------------------

export function getSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  return request<SystemStatus>("/api/v1/system/status", { signal });
}

export function getUiOptions(signal?: AbortSignal): Promise<UIOptions> {
  return request<UIOptions>("/api/v1/config/ui-options", { signal });
}

export interface TechnicalArchitectureResponse {
  title: string;
  source_path: string;
  size_bytes: number;
  markdown: string;
  generated_at: string;
}

export function getTechnicalArchitecture(
  signal?: AbortSignal,
): Promise<TechnicalArchitectureResponse> {
  return request<TechnicalArchitectureResponse>(
    "/api/v1/system/technical-architecture",
    { signal },
  );
}

export function getTechnicalArchitectureMarkdownUrl(): string {
  return `${getActiveApiBaseUrl()}/api/v1/system/technical-architecture.md`;
}

// ---------------------------------------------------------------------------
// Phase 14C — auto-detect API URL at page load
//
// When the dashboard renders, walk a small list of candidate backend
// URLs and pick the first one whose ``/healthz`` returns 200 within a
// short timeout. This insulates the operator from build-time vs.
// runtime URL drift: even if NEXT_PUBLIC_API_BASE_URL was baked at a
// different domain (tunnel, localhost, etc.), the dashboard finds a
// working backend without anyone touching Settings.
// ---------------------------------------------------------------------------

export async function probeBackendHealth(
  baseUrl: string,
  timeoutMs = 2500,
): Promise<boolean> {
  if (!baseUrl) return false;
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const resp = await fetch(`${baseUrl.replace(/\/$/, "")}/healthz`, {
      method: "GET",
      signal: ctrl.signal,
      // Don't send cookies/credentials — every probe must be cheap.
      credentials: "omit",
      cache: "no-store",
    });
    return resp.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(t);
  }
}

export interface CharacterVideoLinkItem {
  id: string;
  job_id: string;
  job_status: string | null;
  provider_id: string | null;
  status: string;
  created_at: string;
  duration_seconds: number | null;
  video_artifact_uri: string | null;
  video_artifact_id: string | null;
}

export interface CharacterVideosResponse {
  items: CharacterVideoLinkItem[];
  total: number;
}

export function getCharacterVideos(
  characterId: string,
  signal?: AbortSignal,
): Promise<CharacterVideosResponse> {
  return request<CharacterVideosResponse>(
    `/api/v1/characters/${characterId}/videos`,
    { signal },
  );
}

export async function autoDetectBackendBaseUrl(
  candidates: readonly string[],
): Promise<string | null> {
  // Dedupe + drop empties while preserving order.
  const seen = new Set<string>();
  const queue: string[] = [];
  for (const c of candidates) {
    const trimmed = (c || "").trim().replace(/\/$/, "");
    if (!trimmed || seen.has(trimmed)) continue;
    seen.add(trimmed);
    queue.push(trimmed);
  }
  for (const url of queue) {
    if (await probeBackendHealth(url)) {
      return url;
    }
  }
  return null;
}

export interface BackendLogEntry {
  seq: number;
  ts: number;
  level: string;
  logger: string;
  message: string;
  extra: Record<string, unknown>;
}

export interface BackendLogsResponse {
  latest_seq: number;
  server_time: string;
  entries: BackendLogEntry[];
}

export function getBackendLogs(
  params: { since_seq?: number; limit?: number } = {},
  signal?: AbortSignal,
): Promise<BackendLogsResponse> {
  const search = new URLSearchParams();
  if (params.since_seq !== undefined) search.set("since_seq", String(params.since_seq));
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const qs = search.toString();
  const path = qs ? `/api/v1/system/logs/backend?${qs}` : "/api/v1/system/logs/backend";
  return request<BackendLogsResponse>(path, { signal });
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export function listJobs(
  params: { limit?: number; offset?: number; status?: JobStatus } = {},
  signal?: AbortSignal,
): Promise<JobSummary[]> {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  if (params.status !== undefined) search.set("status", params.status);
  const qs = search.toString();
  const path = qs ? `/api/v1/jobs?${qs}` : "/api/v1/jobs";
  return request<JobSummary[]>(path, { signal, logLabel: "/api/v1/jobs" });
}

/**
 * Phase 4F-2 aggregate detail. Backwards compatible with the legacy
 * JobResponse shape — every legacy field is preserved on JobDetail, so
 * existing callers that read brief/status/etc keep working unchanged.
 */
export function getJob(jobId: string, signal?: AbortSignal): Promise<JobDetail> {
  return request<JobDetail>(`/api/v1/jobs/${jobId}`, {
    signal,
    logLabel: "/api/v1/jobs/:id",
  });
}

/**
 * Phase 4F-2 combined payload. Single round-trip alternative to fetching
 * the seven detail-page endpoints in parallel.
 */
export function getJobSummary(
  jobId: string,
  signal?: AbortSignal,
): Promise<JobFullSummary> {
  return request<JobFullSummary>(`/api/v1/jobs/${jobId}/summary`, {
    signal,
    logLabel: "/api/v1/jobs/:id/summary",
  });
}

export function getJobProgress(
  jobId: string,
  signal?: AbortSignal,
): Promise<JobProgress> {
  return request<JobProgress>(`/api/v1/jobs/${jobId}/progress`, {
    signal,
    logLabel: "/api/v1/jobs/:id/progress",
  });
}

export function getJobTimeline(
  jobId: string,
  signal?: AbortSignal,
): Promise<StageTimelineEntry[]> {
  return request<StageTimelineEntry[]>(`/api/v1/jobs/${jobId}/timeline`, {
    signal,
    logLabel: "/api/v1/jobs/:id/timeline",
  });
}

export function getJobArtifacts(
  jobId: string,
  signal?: AbortSignal,
): Promise<ArtifactResponse[]> {
  return request<ArtifactResponse[]>(`/api/v1/jobs/${jobId}/artifacts`, {
    signal,
    logLabel: "/api/v1/jobs/:id/artifacts",
  });
}

export function getJobComplianceEvents(
  jobId: string,
  signal?: AbortSignal,
): Promise<ComplianceEventResponse[]> {
  return request<ComplianceEventResponse[]>(
    `/api/v1/jobs/${jobId}/compliance-events`,
    { signal, logLabel: "/api/v1/jobs/:id/compliance-events" },
  );
}

export async function getJobQcReportOptional(
  jobId: string,
  signal?: AbortSignal,
): Promise<QCReportResponse | null> {
  try {
    return await request<QCReportResponse>(`/api/v1/jobs/${jobId}/qc-report`, {
      signal,
      logLabel: "/api/v1/jobs/:id/qc-report",
    });
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export async function getJobFinalExportOptional(
  jobId: string,
  signal?: AbortSignal,
): Promise<FinalExportResponse | null> {
  try {
    return await request<FinalExportResponse>(
      `/api/v1/jobs/${jobId}/final-export`,
      { signal, logLabel: "/api/v1/jobs/:id/final-export" },
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export function createJob(
  body: CreateJobBody,
  signal?: AbortSignal,
): Promise<JobResponse> {
  return request<JobResponse>("/api/v1/jobs", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
    signal,
  });
}

export function createJobFromInputs(
  body: CreateJobFromInputsBody,
  signal?: AbortSignal,
): Promise<JobResponse> {
  return request<JobResponse>("/api/v1/jobs/from-inputs", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
    signal,
  });
}

/**
 * Phase 11B — PATCH /api/v1/jobs/{id}. Accepts the full editable
 * surface: brief, target duration, script, voice/face modes, provider
 * selection (per-category ids + models), language + subtitle settings.
 * The server policy decides which fields are accepted for the current
 * job status (see ``can_edit`` / ``locked_fields`` on JobResponse).
 */
export function updateJob(
  jobId: string,
  patch: JobUpdateBody,
  signal?: AbortSignal,
): Promise<JobResponse> {
  return request<JobResponse>(`/api/v1/jobs/${jobId}`, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify(patch),
    signal,
    logLabel: "/api/v1/jobs/:id",
  });
}

export function deleteJob(jobId: string, signal?: AbortSignal): Promise<void> {
  return request<void>(`/api/v1/jobs/${jobId}`, {
    method: "DELETE",
    signal,
    logLabel: "/api/v1/jobs/:id",
  });
}

// ---------------------------------------------------------------------------
// Phase 8D — operational controls.
// ---------------------------------------------------------------------------

export function cancelJob(
  jobId: string,
  body: { readonly reason?: string | null } = {},
  signal?: AbortSignal,
): Promise<JobResponse> {
  return request<JobResponse>(`/api/v1/jobs/${jobId}/cancel`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ reason: body.reason ?? null }),
    signal,
    logLabel: "/api/v1/jobs/:id/cancel",
  });
}

export function retryJob(
  jobId: string,
  body: {
    readonly stage_name?: string | null;
    readonly reason?: string | null;
  } = {},
  signal?: AbortSignal,
): Promise<JobResponse> {
  return request<JobResponse>(`/api/v1/jobs/${jobId}/retry`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      stage_name: body.stage_name ?? null,
      reason: body.reason ?? null,
    }),
    signal,
    logLabel: "/api/v1/jobs/:id/retry",
  });
}

// ---------------------------------------------------------------------------
// Uploads
// ---------------------------------------------------------------------------

export function uploadText(
  body: {
    readonly script_text: string;
    readonly title?: string | null;
    readonly language?: string;
    readonly tone?: string | null;
    readonly target_duration_seconds?: number | null;
  },
  signal?: AbortSignal,
): Promise<UploadTextResponse> {
  return request<UploadTextResponse>("/api/v1/uploads/text", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
    signal,
  });
}

export function uploadAudio(
  file: File,
  signal?: AbortSignal,
): Promise<UploadAudioResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadAudioResponse>("/api/v1/uploads/audio", {
    method: "POST",
    body: form,
    signal,
  });
}

export function uploadImage(
  file: File,
  signal?: AbortSignal,
): Promise<UploadImageResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadImageResponse>("/api/v1/uploads/image", {
    method: "POST",
    body: form,
    signal,
  });
}

// ---------------------------------------------------------------------------
// Phase 4F: providers + TTS preview + artifact content URLs.
// ---------------------------------------------------------------------------

export function getProviders(signal?: AbortSignal): Promise<ProvidersResponse> {
  return request<ProvidersResponse>("/api/v1/providers", { signal });
}

export function getProvidersForCategory(
  category:
    | "llm"
    | "tts"
    | "video_generator"
    | "audio_processor"
    | "image_processor",
  signal?: AbortSignal,
): Promise<ProviderInfo[]> {
  const slug: string =
    category === "video_generator"
      ? "video-generators"
      : category === "audio_processor"
        ? "audio-processors"
        : category === "image_processor"
          ? "image-processors"
          : category;
  return request<ProviderInfo[]>(`/api/v1/providers/${slug}`, { signal });
}

// Phase 8F-2 — widen the result type so callers (e.g. the Test1
// diagnostics panel) can pattern-match the success branch the backend
// has shipped since Phase 5A.
export type TTSGenerateResult =
  | { readonly ok: true; readonly value: TTSGenerateResponse }
  | {
      readonly ok: false;
      readonly error: TTSGenerateError;
      readonly httpStatus: number;
    };

export async function generateTts(
  body: TTSGenerateRequest,
  signal?: AbortSignal,
): Promise<TTSGenerateResult> {
  try {
    const value = await request<TTSGenerateResponse>("/api/v1/tts/generate", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(body),
      signal,
    });
    return { ok: true, value };
  } catch (err) {
    if (err instanceof ApiError) {
      // The 503 body is JSON-stringified by the request wrapper if not a
      // plain string; try to parse it back.
      let parsed: TTSGenerateError | null = null;
      try {
        parsed = JSON.parse(err.detail) as TTSGenerateError;
      } catch {
        parsed = null;
      }
      return {
        ok: false,
        httpStatus: err.status,
        error:
          parsed ?? {
            code: "tts_provider_not_configured",
            message: err.detail,
            provider_id: body.tts_provider_id,
          },
      };
    }
    throw err;
  }
}

export function artifactContentUrl(
  artifactId: string,
  options?: { readonly download?: boolean },
): string {
  const base = `${getActiveApiBaseUrl()}/api/v1/artifacts/${artifactId}/content`;
  return options?.download ? `${base}?download=true` : base;
}

// ---------------------------------------------------------------------------
// Phase 5B — script generation preview.
// ---------------------------------------------------------------------------

export type ScriptGenerateResult =
  | { readonly ok: true; readonly value: ScriptGenerateResponse }
  | { readonly ok: false; readonly error: ScriptGenerateError; readonly httpStatus: number };

export async function generateScript(
  body: ScriptGenerateRequest,
  signal?: AbortSignal,
): Promise<ScriptGenerateResult> {
  try {
    const value = await request<ScriptGenerateResponse>("/api/v1/script/generate", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(body),
      signal,
    });
    return { ok: true, value };
  } catch (err) {
    if (err instanceof ApiError) {
      let parsed: ScriptGenerateError | null = null;
      try {
        parsed = JSON.parse(err.detail) as ScriptGenerateError;
      } catch {
        parsed = null;
      }
      return {
        ok: false,
        httpStatus: err.status,
        error:
          parsed ?? {
            code: "script_generation_failed",
            message: err.detail,
            provider_id: body.provider_id ?? "template",
          },
      };
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Phase 5C — audio fit-check.
// ---------------------------------------------------------------------------

export function audioFitCheck(
  body: AudioFitCheckRequest,
  signal?: AbortSignal,
): Promise<AudioFitCheckResponse> {
  return request<AudioFitCheckResponse>("/api/v1/audio/fit-check", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
    signal,
  });
}

// ---------------------------------------------------------------------------
// Phase 10C — typed wrappers for endpoints previously called by raw fetch
// or not consumed by the UI today. Mirrors api-surface.md row-for-row so
// future pages can pick them up without re-deriving the request shape.
// ---------------------------------------------------------------------------

/**
 * POST /api/v1/video/generate. Always returns HTTP 200 with a categorised
 * status; the caller pattern-matches on ``status`` + ``error_code``.
 * Real inference requires the SadTalker wrapper service (or in-process
 * torch + weights + GPU). See `docs/runbooks/sadtalker-runtime.md`.
 */
export function generateVideo(
  body: VideoGenerateRequest,
  signal?: AbortSignal,
): Promise<VideoGenerateResponse> {
  return request<VideoGenerateResponse>("/api/v1/video/generate", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
    signal,
  });
}

/**
 * POST /api/v1/qc/inspect — re-runs the QC pipeline against an existing
 * artifact (or the job's latest media). Persists a new QCReport.
 */
export function inspectQc(
  body: QcInspectRequest,
  signal?: AbortSignal,
): Promise<QcInspectResponse> {
  return request<QcInspectResponse>("/api/v1/qc/inspect", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
    signal,
  });
}

/**
 * POST /api/v1/export/finalize — bundle the job's final MP4 with watermark
 * + C2PA, register a `final_export` artifact.
 */
export function finalizeExport(
  body: FinalizeExportRequest,
  signal?: AbortSignal,
): Promise<FinalizeExportResponse> {
  return request<FinalizeExportResponse>("/api/v1/export/finalize", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
    signal,
  });
}

/** GET /api/v1/stages — DAG metadata, used by docs / Test panel. */
export function getStages(signal?: AbortSignal): Promise<StageInfo[]> {
  return request<StageInfo[]>("/api/v1/stages", { signal });
}

/** GET /api/v1/artifact-types — the artifact-type catalog. */
export function getArtifactTypes(
  signal?: AbortSignal,
): Promise<ArtifactTypeInfo[]> {
  return request<ArtifactTypeInfo[]>("/api/v1/artifact-types", { signal });
}

/**
 * GET /api/v1/providers/{category}/{provider_id} — single-provider detail
 * (richer readiness payload than the list endpoint). Category uses the
 * underscore form on this endpoint (``video_generator``, ``audio_processor``,
 * ``image_processor``) — we normalise here.
 */
export function getProviderDetail(
  category:
    | "llm"
    | "tts"
    | "video_generator"
    | "audio_processor"
    | "image_processor",
  providerId: string,
  signal?: AbortSignal,
): Promise<ProviderInfo> {
  return request<ProviderInfo>(
    `/api/v1/providers/${category}/${encodeURIComponent(providerId)}`,
    { signal, logLabel: `/api/v1/providers/${category}/:id` },
  );
}
