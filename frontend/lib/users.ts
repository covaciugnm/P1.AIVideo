// User-management API client (protected super admin only on the backend).
import { getActiveApiBaseUrl } from "./settings";
import { authHeaders, handleUnauthorized, type CurrentUser } from "./auth";
import * as logBus from "./log-bus";

function bc(event: string, meta?: Record<string, unknown>): void {
  logBus.emit({ source: "frontend", level: "info", message: event, meta });
}

export type ManagedUser = CurrentUser & {
  readonly created_at?: string | null;
  readonly last_login_at?: string | null;
  readonly approved_at?: string | null;
  readonly suspended_at?: string | null;
  readonly rejected_at?: string | null;
  readonly deleted_at?: string | null;
};

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${getActiveApiBaseUrl()}${path}`, {
    cache: "no-store",
    ...init,
    headers: { Accept: "application/json", ...(init.headers ?? {}), ...authHeaders() },
  });
  if (res.status === 401) handleUnauthorized();
  const body = (await res.json().catch(() => null)) as unknown;
  if (!res.ok) {
    const detail =
      body && typeof (body as { detail?: unknown }).detail === "string"
        ? (body as { detail: string }).detail
        : `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return body as T;
}

export interface UserListResponse {
  readonly items: readonly ManagedUser[];
  readonly total: number;
}

export function listUsers(status?: string, includeDeleted = false): Promise<UserListResponse> {
  const qs = new URLSearchParams();
  if (status) qs.set("status", status);
  if (includeDeleted) qs.set("include_deleted", "true");
  const q = qs.toString();
  return req<UserListResponse>(`/api/v1/users${q ? `?${q}` : ""}`);
}

const jsonHeaders = { "Content-Type": "application/json" };

export function approveUser(id: string, role: string): Promise<ManagedUser> {
  bc("USER_APPROVE_CLICKED", { id, role });
  return req(`/api/v1/users/${id}/approve`, {
    method: "POST", headers: jsonHeaders, body: JSON.stringify({ role }),
  });
}
export function rejectUser(id: string, reason?: string): Promise<ManagedUser> {
  return req(`/api/v1/users/${id}/reject`, {
    method: "POST", headers: jsonHeaders, body: JSON.stringify({ reason: reason ?? null }),
  });
}
export function suspendUser(id: string, reason?: string): Promise<ManagedUser> {
  bc("USER_SUSPEND_CLICKED", { id });
  return req(`/api/v1/users/${id}/suspend`, {
    method: "POST", headers: jsonHeaders, body: JSON.stringify({ reason: reason ?? null }),
  });
}
export function reactivateUser(id: string): Promise<ManagedUser> {
  return req(`/api/v1/users/${id}/reactivate`, { method: "POST" });
}
export function deleteUser(id: string): Promise<ManagedUser> {
  bc("USER_DELETE_CLICKED", { id });
  return req(`/api/v1/users/${id}`, { method: "DELETE" });
}
