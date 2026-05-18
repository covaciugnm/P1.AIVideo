// Phase 12X — DB-backed API secrets client.

import { ApiError, getActiveApiBaseUrl, humanizeApiDetail } from "./api";

export type SecretCategory =
  | "huggingface"
  | "image_generator"
  | "llm"
  | "tts"
  | "local_endpoint"
  | "misc";

export interface ApiSecret {
  readonly id: number;
  readonly key_name: string;
  readonly value: string;
  readonly description: string | null;
  readonly category: SecretCategory;
  readonly last_tested_at: string | null;
  readonly last_test_status: "ok" | "failed" | "skipped" | null;
  readonly last_test_detail: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ApiSecretCatalogEntry {
  readonly key_name: string;
  readonly description: string;
  readonly category: SecretCategory;
  readonly test_probe: string;
}

export interface ApiSecretListResponse {
  readonly items: readonly ApiSecret[];
  readonly catalog: readonly ApiSecretCatalogEntry[];
}

export interface ApiSecretTestResponse {
  readonly key_name: string;
  readonly status: "ok" | "failed" | "skipped";
  readonly detail: string;
  readonly last_tested_at: string;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(`${getActiveApiBaseUrl()}${path}`, {
    cache: "no-store",
    ...init,
    headers: { Accept: "application/json", ...(init.headers ?? {}) },
  });
  if (r.status === 204) return undefined as T;
  let body: unknown = null;
  try {
    body = await r.json();
  } catch {
    /* leave null */
  }
  if (!r.ok) throw new ApiError(r.status, humanizeApiDetail(body));
  return body as T;
}

export function listSecrets(): Promise<ApiSecretListResponse> {
  return request<ApiSecretListResponse>("/api/v1/secrets");
}

export function saveSecret(
  key_name: string,
  value: string,
  description?: string | null,
  category?: SecretCategory,
): Promise<ApiSecret> {
  return request<ApiSecret>("/api/v1/secrets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      key_name,
      value,
      description: description ?? null,
      category: category ?? "misc",
    }),
  });
}

export function deleteSecret(key_name: string): Promise<void> {
  return request<void>(`/api/v1/secrets/${encodeURIComponent(key_name)}`, {
    method: "DELETE",
  });
}

export function testSecret(key_name: string): Promise<ApiSecretTestResponse> {
  return request<ApiSecretTestResponse>(
    `/api/v1/secrets/${encodeURIComponent(key_name)}/test`,
    { method: "POST" },
  );
}
