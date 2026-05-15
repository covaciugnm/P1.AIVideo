// Phase 6D — frontend-only custom provider metadata.
//
// Custom providers live in localStorage. They register METADATA only —
// the UI never installs packages, never runs shell commands, never
// modifies backend files. When merged with the backend catalog they're
// flagged ``is_custom: true`` so dropdowns can warn that runtime setup
// is still the operator's responsibility.

import type { ProviderCategory, ProviderInfo, ProviderLocality } from "./types";

export const CUSTOM_PROVIDERS_STORAGE_KEY = "aivideo:custom-providers:v1";

/** Phase 6D custom-provider input shape (operator-writable). */
export interface CustomProviderInput {
  readonly category: ProviderCategory;
  readonly provider_id: string;
  readonly label: string;
  readonly backend_type: string;
  readonly local_or_external: ProviderLocality;
  readonly endpoint_url?: string;
  readonly default_model?: string;
  readonly supported_models?: readonly string[];
  readonly requires_network: boolean;
  readonly requires_gpu: boolean;
  readonly requires_model_files: boolean;
  readonly enabled: boolean;
  readonly notes?: string;
}

const SLUG_RE = /^[a-z0-9][a-z0-9_-]{0,79}$/;

/**
 * Validate a custom provider record before persisting.
 *
 * Returns an error message if invalid, or ``null`` if OK. We
 * deliberately refuse anything that looks like a credential in the
 * endpoint URL — the spec forbids API keys / secrets in custom
 * provider records.
 */
export function validateCustomProvider(input: CustomProviderInput): string | null {
  if (!input.provider_id) return "provider_id is required";
  if (!SLUG_RE.test(input.provider_id)) {
    return "provider_id must be lowercase alphanumeric with - or _ (slug-safe)";
  }
  if (!input.label.trim()) return "label is required";
  if (!input.backend_type.trim()) return "backend_type is required";
  if (input.endpoint_url) {
    if (input.endpoint_url.includes("@")) {
      return "endpoint_url contains '@' — credentials in URLs are not allowed";
    }
    if (/Authorization|api[_-]?key|token=/i.test(input.endpoint_url)) {
      return "endpoint_url looks like it carries credentials — strip them";
    }
  }
  return null;
}

/**
 * Project a custom-provider input + storage hint into a {@link ProviderInfo}
 * for the unified UI list. Status defaults to ``disabled`` when the
 * operator unticked ``enabled`` and ``not_configured`` otherwise — the
 * backend can never observe these, so the frontend stages the verdict.
 */
export function customToProviderInfo(input: CustomProviderInput): ProviderInfo {
  return {
    category: input.category,
    provider_id: input.provider_id,
    label: input.label,
    backend_type: input.backend_type,
    default_model: input.default_model ?? null,
    is_local: input.local_or_external === "local",
    local_or_external: input.local_or_external,
    supported_models: input.supported_models ?? [],
    requires_network: input.requires_network,
    requires_gpu: input.requires_gpu,
    requires_model_files: input.requires_model_files,
    healthcheck_available: false,
    notes: input.notes ?? "",
    warning:
      "Custom / metadata only. Installing or configuring the runtime is " +
      "still the operator's responsibility.",
    docs_url: "",
    is_custom: true,
    status: input.enabled ? "not_configured" : "disabled",
  };
}

export function loadCustomProviders(): CustomProviderInput[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(CUSTOM_PROVIDERS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(_isCustomProviderShape);
  } catch {
    return [];
  }
}

export function saveCustomProviders(list: readonly CustomProviderInput[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CUSTOM_PROVIDERS_STORAGE_KEY, JSON.stringify(list));
  } catch {
    // Quota / private mode — ignore.
  }
}

/**
 * Merge backend providers with the operator's localStorage custom
 * providers for a single category. Built-in providers take precedence
 * when an id collision exists; custom providers are appended after.
 */
export function mergeProvidersForCategory(
  category: ProviderCategory,
  builtIn: readonly ProviderInfo[],
  custom: readonly CustomProviderInput[],
): ProviderInfo[] {
  const builtinIds = new Set(builtIn.map((p) => p.provider_id));
  const out: ProviderInfo[] = [...builtIn];
  for (const c of custom) {
    if (c.category !== category) continue;
    if (builtinIds.has(c.provider_id)) continue; // built-in wins
    out.push(customToProviderInfo(c));
  }
  return out;
}

function _isCustomProviderShape(value: unknown): value is CustomProviderInput {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.category === "string" &&
    typeof v.provider_id === "string" &&
    typeof v.label === "string" &&
    typeof v.backend_type === "string" &&
    (v.local_or_external === "local" || v.local_or_external === "external") &&
    typeof v.requires_network === "boolean" &&
    typeof v.requires_gpu === "boolean" &&
    typeof v.requires_model_files === "boolean" &&
    typeof v.enabled === "boolean"
  );
}
