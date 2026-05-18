// Phase 12 — Characters / Personas API client + types.
//
// Mirrors backend/app/schemas/character.py. Every type here is
// metadata-only — image PNGs are served as raw binary via the
// dedicated /images/:id/content endpoint, never inlined in JSON.

import * as logBus from "./log-bus";
import { ApiError, humanizeApiDetail, getActiveApiBaseUrl } from "./api";

// ---------------------------------------------------------------------------
// Profile shape
// ---------------------------------------------------------------------------

export type CharacterStatus = "active" | "inactive" | "draft";

export interface CharacterIdentity {
  readonly name: string;
  readonly display_name?: string | null;
  readonly slug?: string | null;
  readonly gender?: string | null;
  /** ISO date string (YYYY-MM-DD). */
  readonly date_of_birth?: string | null;
  readonly age?: number | null;
  readonly nationality?: string | null;
  readonly native_language?: string | null;
  readonly spoken_languages?: readonly string[];
  readonly marital_status?: string | null;
  readonly place_of_birth?: string | null;
  readonly current_location?: string | null;
  readonly social_status?: string | null;
  readonly is_public_persona?: boolean;
}

export interface CharacterAppearance {
  readonly height?: string | null;
  readonly weight_or_build?: string | null;
  readonly skin_tone?: string | null;
  readonly hair_color?: string | null;
  readonly hair_style?: string | null;
  readonly eye_color?: string | null;
  readonly face_shape?: string | null;
  readonly distinctive_features?: string | null;
  readonly clothing_style?: string | null;
  readonly visual_consistency_notes?: string | null;
  readonly negative_visual_constraints?: string | null;
}

export interface CharacterEducation {
  readonly education_level?: string | null;
  readonly field_of_study?: string | null;
  readonly certifications?: readonly string[];
  readonly occupation?: string | null;
  readonly professional_seniority?: string | null;
  readonly current_role?: string | null;
  readonly previous_roles?: readonly string[];
  readonly cv_summary?: string | null;
  readonly industry_domain?: string | null;
  readonly expertise?: readonly string[];
  readonly authority_level?: string | null;
  readonly reputation_notes?: string | null;
}

export interface CharacterPersonality {
  readonly archetype?: string | null;
  readonly communication_style?: string | null;
  readonly temperament?: string | null;
  readonly emotional_tone?: string | null;
  readonly confidence_level?: string | null;
  readonly humor_level?: string | null;
  readonly formality_level?: string | null;
  readonly empathy_level?: string | null;
  readonly assertiveness_level?: string | null;
  readonly patience_level?: string | null;
  readonly moral_values?: string | null;
  readonly fears?: string | null;
  readonly motivations?: string | null;
  readonly goals?: string | null;
  readonly conflict_style?: string | null;
  readonly decision_style?: string | null;
  readonly narrative_role?: string | null;
}

export interface CharacterVoice {
  readonly preferred_language?: string | null;
  readonly accent?: string | null;
  readonly voice_gender?: string | null;
  readonly voice_age?: string | null;
  readonly speaking_speed?: string | null;
  readonly pitch?: string | null;
  readonly tone?: string | null;
  readonly preferred_tts_provider_id?: string | null;
  readonly f5tts_profile?: string | null;
  readonly voice_sample_library_ref?: string | null;
}

export interface CharacterScriptBehaviour {
  readonly default_role_in_videos?: string | null;
  readonly default_speaking_duration_seconds?: number | null;
  readonly default_camera_framing?: string | null;
  readonly default_mood?: string | null;
  readonly default_background?: string | null;
  readonly default_topic_expertise?: string | null;
  readonly allowed_topics?: readonly string[];
  readonly blocked_topics?: readonly string[];
  readonly safety_notes?: string | null;
  readonly prompt_style_notes?: string | null;
  readonly script_generation_notes?: string | null;
}

export interface CharacterProfile {
  readonly identity: CharacterIdentity;
  readonly appearance: CharacterAppearance;
  readonly education: CharacterEducation;
  readonly personality: CharacterPersonality;
  readonly voice: CharacterVoice;
  readonly script_behaviour: CharacterScriptBehaviour;
}

export interface CharacterSummary {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
  readonly display_name: string | null;
  readonly status: CharacterStatus;
  readonly default_language: string | null;
  readonly default_voice_provider_id: string | null;
  readonly default_image_provider_id: string | null;
  readonly main_reference_image_id: string | null;
  // Phase 16 — once true, main_reference is frozen and cannot be re-pointed.
  readonly face_locked?: boolean;
  readonly image_count: number;
  readonly video_count: number;
  readonly version_number: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface CharacterResponse extends CharacterSummary {
  readonly profile: CharacterProfile;
  readonly deleted_at?: string | null;
}

export interface CharacterListResponse {
  readonly items: readonly CharacterSummary[];
  readonly total: number;
}

export interface CharacterCreateRequest {
  readonly profile: CharacterProfile;
  readonly slug?: string | null;
  readonly status?: CharacterStatus;
  readonly default_language?: string | null;
  readonly default_voice_provider_id?: string | null;
  readonly default_image_provider_id?: string | null;
}

export type CharacterUpdateRequest = Partial<CharacterCreateRequest>;

// ---------------------------------------------------------------------------
// Lookups (translatable dropdowns)
// ---------------------------------------------------------------------------

export interface LookupOption {
  readonly value: string;
  readonly label_key: string;
  readonly label_en: string;
  readonly label_ro: string;
}

export interface CharacterLookupsResponse {
  readonly gender: readonly LookupOption[];
  readonly marital_status: readonly LookupOption[];
  readonly education_level: readonly LookupOption[];
  readonly social_status: readonly LookupOption[];
  readonly professional_seniority: readonly LookupOption[];
  readonly authority_level: readonly LookupOption[];
  readonly personality_archetype: readonly LookupOption[];
  readonly communication_style: readonly LookupOption[];
  readonly temperament: readonly LookupOption[];
  readonly emotional_tone: readonly LookupOption[];
  readonly level_scale: readonly LookupOption[];
  readonly conflict_style: readonly LookupOption[];
  readonly decision_style: readonly LookupOption[];
  readonly narrative_role: readonly LookupOption[];
  readonly voice_gender: readonly LookupOption[];
  readonly voice_age: readonly LookupOption[];
  readonly speaking_speed: readonly LookupOption[];
  readonly pitch: readonly LookupOption[];
  readonly tone: readonly LookupOption[];
  readonly camera_framing: readonly LookupOption[];
  readonly mood: readonly LookupOption[];
  readonly character_status: readonly LookupOption[];
  readonly image_status: readonly LookupOption[];
  readonly language: readonly LookupOption[];
}

// ---------------------------------------------------------------------------
// Image library
// ---------------------------------------------------------------------------

export type ImageStatus =
  | "draft"
  | "accepted"
  | "rejected"
  | "reference"
  | "archived";

export interface CharacterImageResponse {
  readonly id: string;
  readonly character_id: string;
  readonly file_path: string | null;
  readonly local_url: string | null;
  readonly prompt: string | null;
  readonly negative_prompt: string | null;
  readonly provider_id: string | null;
  readonly model_id: string | null;
  readonly seed: number | null;
  readonly settings_json: Record<string, unknown> | null;
  readonly status: ImageStatus;
  readonly is_main_reference: boolean;
  readonly width: number | null;
  readonly height: number | null;
  readonly size_bytes: number | null;
  readonly checksum_sha256: string | null;
  readonly notes: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface CharacterImageListResponse {
  readonly items: readonly CharacterImageResponse[];
  readonly total: number;
}

export interface CharacterImageGenerateRequest {
  readonly prompt?: string | null;
  readonly negative_prompt?: string | null;
  readonly provider_id: string;
  readonly model_id?: string | null;
  readonly seed?: number | null;
  readonly width?: number;
  readonly height?: number;
  readonly steps?: number | null;
  readonly guidance_scale?: number | null;
  readonly reference_image_id?: string | null;
  readonly use_main_reference?: boolean;
  readonly notes?: string | null;
}

export interface CharacterImageGenerateError {
  readonly error_code:
    | "provider_not_implemented"
    | "provider_not_configured"
    | "provider_unavailable"
    | "runtime_missing"
    | "assets_missing"
    | "gpu_unavailable"
    | "reference_image_missing"
    | "validation_failed"
    | "generation_failed"
    | "storage_failed"
    | "rate_limited";
  readonly detail: string;
  readonly provider_id: string;
  readonly fallback: string | null;
}

export interface CharacterImageActionResponse {
  readonly image: CharacterImageResponse;
  readonly character_main_reference_image_id: string | null;
}

export interface CharacterScriptContextResponse {
  readonly character_id: string;
  readonly text: string;
  readonly fields: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

async function request<T>(
  path: string,
  init: RequestInit & { readonly logLabel?: string } = {},
): Promise<T> {
  const base = getActiveApiBaseUrl();
  const url = `${base}${path}`;
  const label = init.logLabel ?? path;
  const t0 = performance.now();
  const response = await fetch(url, {
    cache: "no-store",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.headers ?? {}),
    },
  });
  const elapsed = Math.round(performance.now() - t0);
  if (response.status === 204) {
    logBus.emit({
      source: "api",
      level: "info",
      message: `${label} → 204 (${elapsed} ms)`,
    });
    return undefined as T;
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    /* leave null */
  }
  if (!response.ok) {
    logBus.emit({
      source: "api",
      level: "warning",
      message: `${label} → HTTP ${response.status} (${elapsed} ms)`,
    });
    throw new ApiError(response.status, humanizeApiDetail(body));
  }
  logBus.emit({
    source: "api",
    level: "info",
    message: `${label} → ${response.status} (${elapsed} ms)`,
  });
  return body as T;
}

function jsonHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

export function listCharacters(signal?: AbortSignal): Promise<CharacterListResponse> {
  return request<CharacterListResponse>(`/api/v1/characters`, {
    signal,
    logLabel: "/api/v1/characters",
  });
}

export function getCharacterLookups(
  signal?: AbortSignal,
): Promise<CharacterLookupsResponse> {
  return request<CharacterLookupsResponse>(`/api/v1/characters/lookups`, {
    signal,
    logLabel: "/api/v1/characters/lookups",
  });
}

export function getCharacter(
  id: string,
  signal?: AbortSignal,
): Promise<CharacterResponse> {
  return request<CharacterResponse>(`/api/v1/characters/${id}`, {
    signal,
    logLabel: "/api/v1/characters/:id",
  });
}

export function createCharacter(
  body: CharacterCreateRequest,
  signal?: AbortSignal,
): Promise<CharacterResponse> {
  return request<CharacterResponse>(`/api/v1/characters`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
    signal,
    logLabel: "POST /api/v1/characters",
  });
}

export function updateCharacter(
  id: string,
  body: CharacterUpdateRequest,
  signal?: AbortSignal,
): Promise<CharacterResponse> {
  return request<CharacterResponse>(`/api/v1/characters/${id}`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
    signal,
    logLabel: "PUT /api/v1/characters/:id",
  });
}

export function deleteCharacter(
  id: string,
  signal?: AbortSignal,
): Promise<CharacterResponse> {
  return request<CharacterResponse>(`/api/v1/characters/${id}`, {
    method: "DELETE",
    signal,
    logLabel: "DELETE /api/v1/characters/:id",
  });
}

export function listCharacterImages(
  characterId: string,
  signal?: AbortSignal,
): Promise<CharacterImageListResponse> {
  return request<CharacterImageListResponse>(
    `/api/v1/characters/${characterId}/images`,
    { signal, logLabel: "/api/v1/characters/:id/images" },
  );
}

export type CharacterImageGenerateResult =
  | { readonly ok: true; readonly value: CharacterImageResponse }
  | {
      readonly ok: false;
      readonly error: CharacterImageGenerateError;
      readonly httpStatus: number;
    };

export async function generateCharacterImage(
  characterId: string,
  body: CharacterImageGenerateRequest,
  signal?: AbortSignal,
): Promise<CharacterImageGenerateResult> {
  try {
    const value = await request<CharacterImageResponse>(
      `/api/v1/characters/${characterId}/images/generate`,
      {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(body),
        signal,
        logLabel: "POST /api/v1/characters/:id/images/generate",
      },
    );
    return { ok: true, value };
  } catch (err) {
    if (err instanceof ApiError) {
      try {
        const parsed = JSON.parse(err.detail) as CharacterImageGenerateError;
        if (parsed && typeof parsed === "object" && "error_code" in parsed) {
          return { ok: false, error: parsed, httpStatus: err.status };
        }
      } catch {
        /* fall-through */
      }
      return {
        ok: false,
        error: {
          error_code: "generation_failed",
          detail: err.detail,
          provider_id: body.provider_id,
          fallback: "mock",
        },
        httpStatus: err.status,
      };
    }
    throw err;
  }
}

export function setCharacterImageStatus(
  characterId: string,
  imageId: string,
  action: "accept" | "reject" | "set-main-reference" | "archive",
  signal?: AbortSignal,
): Promise<CharacterImageActionResponse> {
  return request<CharacterImageActionResponse>(
    `/api/v1/characters/${characterId}/images/${imageId}/${action}`,
    {
      method: "POST",
      signal,
      logLabel: `POST /api/v1/characters/:id/images/:imageId/${action}`,
    },
  );
}

export function deleteCharacterImage(
  characterId: string,
  imageId: string,
  signal?: AbortSignal,
): Promise<void> {
  return request<void>(
    `/api/v1/characters/${characterId}/images/${imageId}`,
    {
      method: "DELETE",
      signal,
      logLabel: "DELETE /api/v1/characters/:id/images/:imageId",
    },
  );
}

export function getCharacterScriptContext(
  characterId: string,
  signal?: AbortSignal,
): Promise<CharacterScriptContextResponse> {
  return request<CharacterScriptContextResponse>(
    `/api/v1/characters/${characterId}/script-context`,
    { signal, logLabel: "/api/v1/characters/:id/script-context" },
  );
}

export function characterImageContentUrl(
  characterId: string,
  imageId: string,
): string {
  return `${getActiveApiBaseUrl()}/api/v1/characters/${characterId}/images/${imageId}/content`;
}

export function makeEmptyProfile(): CharacterProfile {
  return {
    identity: {
      name: "",
      spoken_languages: [],
      is_public_persona: false,
    },
    appearance: {},
    education: { certifications: [], previous_roles: [], expertise: [] },
    personality: {},
    voice: {},
    script_behaviour: { allowed_topics: [], blocked_topics: [] },
  };
}
