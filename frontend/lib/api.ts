// Typed API client.
//
// One function per endpoint. Every backend route the UI consumes is
// declared here so that pages/components don't sprinkle raw `fetch`
// calls across the codebase.

import type {
  ArtifactResponse,
  ComplianceEventResponse,
  CreateJobBody,
  CreateJobFromInputsBody,
  FinalExportResponse,
  JobProgress,
  JobResponse,
  JobSummary,
  QCReportResponse,
  StageTimelineEntry,
  SystemStatus,
  UIOptions,
  UploadAudioResponse,
  UploadImageResponse,
  UploadTextResponse,
} from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
  readonly method?: "GET" | "POST";
  readonly body?: BodyInit | null;
  readonly headers?: Record<string, string>;
  readonly signal?: AbortSignal;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const init: RequestInit = {
    method: opts.method ?? "GET",
    headers: opts.headers,
    signal: opts.signal,
    cache: "no-store",
  };
  if (opts.body !== undefined && opts.body !== null) {
    init.body = opts.body;
  }
  const response = await fetch(url, init);
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
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
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
  params: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<JobSummary[]> {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  const qs = search.toString();
  const path = qs ? `/api/v1/jobs?${qs}` : "/api/v1/jobs";
  return request<JobSummary[]>(path, { signal });
}

export function getJob(jobId: string, signal?: AbortSignal): Promise<JobResponse> {
  return request<JobResponse>(`/api/v1/jobs/${jobId}`, { signal });
}

export function getJobProgress(
  jobId: string,
  signal?: AbortSignal,
): Promise<JobProgress> {
  return request<JobProgress>(`/api/v1/jobs/${jobId}/progress`, { signal });
}

export function getJobTimeline(
  jobId: string,
  signal?: AbortSignal,
): Promise<StageTimelineEntry[]> {
  return request<StageTimelineEntry[]>(`/api/v1/jobs/${jobId}/timeline`, {
    signal,
  });
}

export function getJobArtifacts(
  jobId: string,
  signal?: AbortSignal,
): Promise<ArtifactResponse[]> {
  return request<ArtifactResponse[]>(`/api/v1/jobs/${jobId}/artifacts`, {
    signal,
  });
}

export function getJobComplianceEvents(
  jobId: string,
  signal?: AbortSignal,
): Promise<ComplianceEventResponse[]> {
  return request<ComplianceEventResponse[]>(
    `/api/v1/jobs/${jobId}/compliance-events`,
    { signal },
  );
}

export async function getJobQcReportOptional(
  jobId: string,
  signal?: AbortSignal,
): Promise<QCReportResponse | null> {
  try {
    return await request<QCReportResponse>(`/api/v1/jobs/${jobId}/qc-report`, {
      signal,
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
      { signal },
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
