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
  AudioFitCheckRequest,
  AudioFitCheckResponse,
  ComplianceEventResponse,
  CreateJobBody,
  CreateJobFromInputsBody,
  FinalExportResponse,
  JobDetail,
  JobFullSummary,
  JobProgress,
  JobResponse,
  JobStatus,
  JobSummary,
  ProviderInfo,
  ProvidersResponse,
  QCReportResponse,
  ScriptGenerateError,
  ScriptGenerateRequest,
  ScriptGenerateResponse,
  StageTimelineEntry,
  SystemStatus,
  TTSGenerateError,
  TTSGenerateRequest,
  UIOptions,
  UploadAudioResponse,
  UploadImageResponse,
  UploadTextResponse,
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

export function updateJob(
  jobId: string,
  patch: Partial<{
    brief: string;
    target_duration_seconds: number;
    script_text: string;
    voice_mode: "tts" | "provided_audio";
    face_mode: "provided_image" | null;
    tts_backend: string;
    watermark_required: boolean;
    c2pa_required: boolean;
  }>,
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
  category: "llm" | "tts" | "video_generator",
  signal?: AbortSignal,
): Promise<ProviderInfo[]> {
  const path =
    category === "video_generator"
      ? "/api/v1/providers/video-generators"
      : `/api/v1/providers/${category}`;
  return request<ProviderInfo[]>(path, { signal });
}

export interface TTSGenerateResult {
  readonly ok: false;
  readonly error: TTSGenerateError;
  readonly httpStatus: number;
}

export async function generateTts(
  body: TTSGenerateRequest,
  signal?: AbortSignal,
): Promise<TTSGenerateResult> {
  try {
    await request<unknown>("/api/v1/tts/generate", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(body),
      signal,
    });
    // No real provider is implemented in Phase 4F — every call should
    // result in the 503 branch below. Reaching here means a future phase
    // wired generation and the caller should be updated to handle it.
    return {
      ok: false,
      httpStatus: 200,
      error: {
        code: "tts_provider_not_implemented",
        message: "TTS generation succeeded but the result schema is not yet wired.",
        provider_id: body.tts_provider_id,
      },
    };
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

export function artifactContentUrl(artifactId: string): string {
  return `${getActiveApiBaseUrl()}/api/v1/artifacts/${artifactId}/content`;
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
