// Auth client — token + current-user storage (dev phase: localStorage).
// Shared by lib/api.ts and lib/characters.ts request layers.

import { getActiveApiBaseUrl } from "./settings";
import * as logBus from "./log-bus";

// Safe frontend breadcrumb (NEVER logs password/token/secret).
function bc(event: string, level: "info" | "success" | "warning" | "error", meta?: Record<string, unknown>): void {
  logBus.emit({ source: "frontend", level, message: event, meta });
}

const TOKEN_KEY = "p1_access_token";
const USER_KEY = "p1_current_user";

export interface CurrentUser {
  readonly id: string;
  readonly username: string;
  readonly email?: string | null;
  readonly full_name?: string | null;
  readonly role: "super_admin" | "admin" | "operator" | "viewer";
  readonly user_status: string;
  readonly is_active: boolean;
  readonly is_protected: boolean;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getCurrentUser(): CurrentUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as CurrentUser;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: CurrentUser): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export function isProtectedSuperAdmin(u: CurrentUser | null): boolean {
  return !!u && u.is_protected && u.role === "super_admin" && u.user_status === "active";
}

/** On 401, clear the session and bounce to /login (preserving nothing). */
export function handleUnauthorized(): void {
  if (typeof window === "undefined") return;
  clearSession();
  if (!window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
}

// --- auth API calls ---------------------------------------------------------

export interface LoginResult {
  readonly access_token: string;
  readonly token_type: string;
  readonly expires_in: number;
  readonly user: CurrentUser;
}

export async function login(username: string, password: string): Promise<LoginResult> {
  bc("LOGIN_SUBMIT", "info", { username });
  const res = await fetch(`${getActiveApiBaseUrl()}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
    cache: "no-store",
  });
  const body = (await res.json().catch(() => null)) as Record<string, unknown> | null;
  if (!res.ok) {
    const detail = body && typeof body.detail === "string" ? body.detail : "Login failed.";
    bc("LOGIN_FAILED", "warning", { username, status: res.status });
    throw new Error(detail);
  }
  bc("LOGIN_SUCCESS", "success", { username });
  return body as unknown as LoginResult;
}

export async function register(
  username: string, email: string, full_name: string, password: string,
): Promise<{ status: string; message: string }> {
  bc("REGISTER_SUBMIT", "info", { username });
  const res = await fetch(`${getActiveApiBaseUrl()}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, email, full_name, password }),
    cache: "no-store",
  });
  const body = (await res.json().catch(() => null)) as Record<string, unknown> | null;
  if (!res.ok) {
    const detail = body && typeof body.detail === "string" ? body.detail : "Registration failed.";
    bc("REGISTER_FAILED", "warning", { username, status: res.status });
    throw new Error(detail);
  }
  bc("REGISTER_SUCCESS_PENDING", "success", { username });
  return body as { status: string; message: string };
}

export function logout(): void {
  bc("LOGOUT_CLICKED", "info");
  clearSession();
  if (typeof window !== "undefined") window.location.href = "/login";
}
