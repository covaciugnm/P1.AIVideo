// Phase 11A-FIX — translation helpers for technical enum values.
//
// The legacy ``humanize()`` helper takes ``pending_compliance`` →
// ``"Pending Compliance"`` which leaks English into the Romanian UI.
// These helpers route every operator-visible enum through the i18n
// dictionary instead, with a final ``humanize()`` fallback only for
// values we haven't translated yet — so the UI never displays a raw
// snake_case identifier either.

import { humanize } from "@/lib/format";

import type { TParams } from "./LanguageContext";

type Translator = (path: string, params?: TParams) => string;

function lookupOr(
  t: Translator,
  section: string,
  value: string | null | undefined,
  unknownKey?: string,
): string {
  if (value === null || value === undefined || value === "") {
    return unknownKey ? t(unknownKey) : "—";
  }
  const path = `${section}.${value}`;
  const translated = t(path);
  // ``t()`` returns the raw path when the key is missing — that's our
  // signal to fall back to a humanised display so the operator never
  // sees ``pending_compliance.something``.
  if (translated === path) {
    return unknownKey ? `${t(unknownKey)} (${humanize(value)})` : humanize(value);
  }
  return translated;
}

/** Translate a job-level status code (``pending_compliance``,
 * ``rejected``, …). Falls back to ``statuses.unknown``. */
export function tStatus(t: Translator, status: string | null | undefined): string {
  return lookupOr(t, "statuses", status, "statuses.unknown");
}

/** Translate a DAG stage name. Falls back to ``stages.pending`` for
 * unknown values so the UI displays a sensible placeholder. */
export function tStage(t: Translator, stage: string | null | undefined): string {
  return lookupOr(t, "stages", stage);
}

/** Translate an artifact type code (``script``, ``audio``, ``video``,
 * …). */
export function tArtifactType(
  t: Translator,
  artifactType: string | null | undefined,
): string {
  return lookupOr(t, "artifactTypes", artifactType, "artifactTypes.unknown");
}

/** Translate a voice mode (``tts``, ``provided_audio``). */
export function tVoiceMode(t: Translator, mode: string | null | undefined): string {
  return lookupOr(t, "voiceModes", mode);
}

/** Translate a face mode (``provided_image``). ``null`` / empty
 * returns the localized "no face" label. */
export function tFaceMode(t: Translator, mode: string | null | undefined): string {
  if (mode === null || mode === undefined || mode === "") {
    return t("faceModes.none");
  }
  return lookupOr(t, "faceModes", mode);
}

/** Translate a provider readiness status (``available``,
 * ``not_configured``, …). */
export function tProviderStatus(
  t: Translator,
  status: string | null | undefined,
): string {
  return lookupOr(t, "providerStatuses", status, "providerStatuses.unknown");
}

/** Translate a compliance gate / event_type. Same data set as
 * ``stages.*`` because gates and stages share names today, but kept as
 * a dedicated wrapper so the call site reads as "compliance gate name"
 * rather than "stage name". */
export function tComplianceGate(
  t: Translator,
  gate: string | null | undefined,
): string {
  return lookupOr(t, "stages", gate);
}

/** Translate a runtime/categorised error code emitted by the backend
 * (``tts_runtime_missing``, ``video_provider_not_implemented``, …).
 * The ``errors.*`` dictionary section is the source of truth. */
export function tRuntimeCode(
  t: Translator,
  code: string | null | undefined,
): string {
  if (!code) return t("common.error");
  const path = `errors.${code}`;
  const translated = t(path);
  if (translated === path) return humanize(code);
  return translated;
}

/** Translate the audio-fit status enum. */
export function tAudioFit(t: Translator, status: string | null | undefined): string {
  const map: Readonly<Record<string, string>> = {
    ok: "runtime.audioFitOk",
    too_short: "runtime.audioFitTooShort",
    too_long: "runtime.audioFitTooLong",
    missing_audio: "runtime.audioFitMissingAudio",
  };
  const key = status ? map[status] : undefined;
  return key ? t(key) : humanize(status ?? "unknown");
}

/** Translate the audio-fit recommendation enum. */
export function tAudioFitRecommendation(
  t: Translator,
  rec: string | null | undefined,
): string {
  const map: Readonly<Record<string, string>> = {
    accept: "runtime.audioFitRecAccept",
    regenerate_script_shorter: "runtime.audioFitRecRegenScriptShorter",
    regenerate_script_longer: "runtime.audioFitRecRegenScriptLonger",
    adjust_target_duration: "runtime.audioFitRecAdjustDuration",
    upload_better_audio: "runtime.audioFitRecUploadBetterAudio",
  };
  const key = rec ? map[rec] : undefined;
  return key ? t(key) : humanize(rec ?? "unknown");
}

/** Localised relative-time formatter. Replaces the English-only
 * ``formatRelative()`` in ``frontend/lib/format.ts``: visible time
 * strings in the dashboard go through this helper so Romanian users
 * see "acum 5 minute" instead of "5m ago". */
export function formatRelativeLocalized(
  t: Translator,
  iso: string | null | undefined,
): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diff = Date.now() - d.getTime();
  const sec = Math.round(diff / 1000);
  if (Math.abs(sec) < 10) return t("time.justNow");
  if (sec < 60) return t("time.secondsAgo", { count: sec });
  const min = Math.round(sec / 60);
  if (min < 60) return t("time.minutesAgo", { count: min });
  const hr = Math.round(min / 60);
  if (hr < 24) return t("time.hoursAgo", { count: hr });
  const day = Math.round(hr / 24);
  return t("time.daysAgo", { count: day });
}

// ---------------------------------------------------------------------
// Backend / Pydantic validation error localization.
// ---------------------------------------------------------------------

/** Known Pydantic v2 ``loc`` paths → translation keys. Each entry
 * matches the trailing fragment of the location list (e.g. the field
 * name itself). */
const FIELD_VALIDATION_KEY: Readonly<Record<string, string>> = {
  synthetic_person_confirmed: "validation.syntheticPersonRequired",
  consent_confirmed: "validation.consentRequired",
  watermark_required: "validation.watermarkRequiredTrue",
  c2pa_required: "validation.c2paRequiredTrue",
};

/** Pydantic / Romanian-message fragments that map to a known
 * translation. Matched as substrings, case-sensitive, so order
 * matters: more specific phrases come before the generic ones. */
const MESSAGE_PATTERNS: ReadonlyArray<{ pattern: RegExp; key: string }> = [
  {
    pattern: /script_text\s+is\s+required\s+when\s+voice_mode='tts'/i,
    key: "validation.scriptTextRequiredForTts",
  },
  {
    pattern: /synthetic_person_confirmed\s+must\s+be\s+true/i,
    key: "validation.syntheticPersonRequired",
  },
  {
    pattern: /consent_confirmed\s+must\s+be\s+true/i,
    key: "validation.consentRequired",
  },
  {
    pattern: /watermark_required\s+must\s+be\s+true/i,
    key: "validation.watermarkRequiredTrue",
  },
  {
    pattern: /c2pa_required\s+must\s+be\s+true/i,
    key: "validation.c2paRequiredTrue",
  },
  {
    pattern:
      /target_duration_seconds\s+must\s+be\s+between\s+(\d+)\s+and\s+(\d+)/i,
    key: "validation.targetDurationRange",
  },
  {
    pattern: /language\s+code\s+.*\s+is\s+not\s+supported/i,
    key: "validation.languageNotSupported",
  },
  {
    pattern: /^job not found/i,
    key: "validation.unknownJob",
  },
];

/** Phase 11A-FIX — turn a raw FastAPI / Pydantic error blob into a
 * localized, operator-readable string. The legacy ``humanizeApiDetail``
 * function in ``lib/api.ts`` produced English-only output; this
 * helper routes the same shapes through the i18n dictionary, falling
 * back to the original English text only for messages we haven't
 * mapped yet.
 *
 * Shapes handled:
 * 1. Plain string ("job not found").
 * 2. ``{"detail": "..."}``.
 * 3. ``{"detail": [ {loc, msg, type}, ... ]}`` — Pydantic v2.
 * 4. ``ApiError`` instances with a ``detail`` string field (we read
 *    the field and re-enter).
 */
export function localizeApiDetail(
  t: Translator,
  raw: unknown,
): string {
  // Unwrap ApiError-like objects.
  if (raw && typeof raw === "object" && "detail" in (raw as object)) {
    const detail = (raw as { detail?: unknown }).detail;
    if (detail !== undefined && detail !== raw) return localizeApiDetail(t, detail);
  }
  if (typeof raw === "string") {
    // Try to parse JSON-stringified payloads.
    try {
      const parsed = JSON.parse(raw);
      return localizeApiDetail(t, parsed);
    } catch {
      return translateMessage(t, raw);
    }
  }
  if (Array.isArray(raw)) {
    const lines: string[] = [];
    for (const item of raw) {
      lines.push(translatePydanticItem(t, item));
    }
    if (lines.length > 0) return lines.join("; ");
  }
  if (raw && typeof raw === "object") {
    try {
      return JSON.stringify(raw);
    } catch {
      return String(raw);
    }
  }
  return String(raw);
}

function translatePydanticItem(t: Translator, item: unknown): string {
  if (!item || typeof item !== "object") return String(item);
  const it = item as Record<string, unknown>;
  const loc = Array.isArray(it["loc"]) ? (it["loc"] as unknown[]).map(String) : [];
  const msg = typeof it["msg"] === "string" ? (it["msg"] as string) : "";
  const type = typeof it["type"] === "string" ? (it["type"] as string) : "";

  if (type === "extra_forbidden") {
    const field = loc.length > 0 ? loc[loc.length - 1] : "?";
    return t("validation.extraForbiddenField", { field });
  }
  if (type === "missing") {
    return t("validation.required");
  }
  if (type === "enum") {
    return t("validation.invalidEnum");
  }

  // Field-specific overrides (matches the deepest path fragment).
  for (let i = loc.length - 1; i >= 0; i -= 1) {
    const key = FIELD_VALIDATION_KEY[loc[i]];
    if (key) return t(key);
  }

  // Message-fragment overrides.
  if (msg) {
    const translated = translateMessage(t, msg, loc);
    if (translated !== msg) return translated;
    return loc.length > 0 ? `${loc.join(".")}: ${translated}` : translated;
  }
  return loc.length > 0 ? `${loc.join(".")}: ${t("validation.invalidType")}` : t("validation.invalidType");
}

function translateMessage(
  t: Translator,
  msg: string,
  loc: readonly string[] = [],
): string {
  for (const { pattern, key } of MESSAGE_PATTERNS) {
    const m = msg.match(pattern);
    if (m) {
      if (key === "validation.targetDurationRange") {
        return t(key, { min: m[1], max: m[2] });
      }
      if (key === "validation.providerSelectionInvalidKey") {
        return t(key, { field: loc[loc.length - 1] ?? "?" });
      }
      return t(key);
    }
  }
  // No mapping — return the raw message so the operator at least sees
  // something diagnosable. Tag with loc when present.
  return loc.length > 0 ? `${loc.join(".")}: ${msg}` : msg;
}
