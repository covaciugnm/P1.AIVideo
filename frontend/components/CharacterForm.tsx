"use client";

// Phase 12 — Character profile form.
//
// Renders every field defined on ``CharacterProfile`` with translated
// labels, localized dropdown options sourced from
// ``/api/v1/characters/lookups``, and provider dropdowns (TTS + image)
// sourced from ``/api/v1/providers`` with green/red status badges.
//
// The form deliberately uses simple HTML controls (select, input,
// textarea) to keep bundle size small and reading the values out
// trivial. Per the parent's onChange callback every keystroke produces
// a complete CharacterProfile so the parent can decide when to POST.

import { useEffect, useMemo, useState } from "react";

import { HelpHint } from "@/components/HelpHint";
import { ProviderStatusBadge } from "@/components/ProviderStatusBadge";
import {
  type CharacterLookupsResponse,
  type CharacterProfile,
  type CharacterStatus,
  type LookupOption,
  getCharacterLookups,
  makeEmptyProfile,
} from "@/lib/characters";
import { useT } from "@/lib/i18n/LanguageContext";
import * as api from "@/lib/api";
import type { ProviderInfo, ProvidersResponse } from "@/lib/types";

export interface CharacterFormValue {
  readonly profile: CharacterProfile;
  readonly status: CharacterStatus;
  readonly default_language: string;
  readonly default_voice_provider_id: string;
  readonly default_image_provider_id: string;
}

export function makeDefaultFormValue(): CharacterFormValue {
  return {
    profile: makeEmptyProfile(),
    // Phase 23 — new characters start in "editing" so identity + voice
    // stay mutable until the operator explicitly activates them.
    status: "editing",
    default_language: "",
    default_voice_provider_id: "",
    default_image_provider_id: "",
  };
}

interface Props {
  readonly value: CharacterFormValue;
  readonly onChange: (next: CharacterFormValue) => void;
  readonly readOnly?: boolean;
  /**
   * Phase 23 — TTS voice provider_ids the character may pick (those not
   * reserved by another active/editing character, plus its own). When
   * provided, the voice dropdown is filtered to this set. ``null`` means
   * "not loaded yet" → show the full list.
   */
  readonly availableVoices?: readonly string[] | null;
  /**
   * Phase 23 — when true (character is active) identity (gender + date of
   * birth) and the TTS voice are immutable. Move the character back to
   * "editing" to change them.
   */
  readonly identityLocked?: boolean;
}

export function CharacterForm({
  value,
  onChange,
  readOnly,
  availableVoices,
  identityLocked,
}: Props) {
  const t = useT();
  const [lookups, setLookups] = useState<CharacterLookupsResponse | null>(null);
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [lk, pr] = await Promise.all([getCharacterLookups(), api.getProviders()]);
        if (cancelled) return;
        setLookups(lk);
        setProviders(pr);
      } catch (err) {
        if (cancelled) return;
        setLoadError((err as Error).message);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  // ----- field setters ----------------------------------------------------

  const setProfile = (next: CharacterProfile) => onChange({ ...value, profile: next });
  const setIdentity = (patch: Partial<CharacterProfile["identity"]>) =>
    setProfile({ ...value.profile, identity: { ...value.profile.identity, ...patch } });
  const setAppearance = (patch: Partial<CharacterProfile["appearance"]>) =>
    setProfile({ ...value.profile, appearance: { ...value.profile.appearance, ...patch } });
  const setEducation = (patch: Partial<CharacterProfile["education"]>) =>
    setProfile({ ...value.profile, education: { ...value.profile.education, ...patch } });
  const setPersonality = (patch: Partial<CharacterProfile["personality"]>) =>
    setProfile({ ...value.profile, personality: { ...value.profile.personality, ...patch } });
  const setVoice = (patch: Partial<CharacterProfile["voice"]>) =>
    setProfile({ ...value.profile, voice: { ...value.profile.voice, ...patch } });
  const setBehaviour = (patch: Partial<CharacterProfile["script_behaviour"]>) =>
    setProfile({
      ...value.profile,
      script_behaviour: { ...value.profile.script_behaviour, ...patch },
    });

  // ----- helpers ----------------------------------------------------------

  const optionLabel = (opt: LookupOption) => t(opt.label_key);

  const renderSelect = (
    label: string,
    helpSlug: string | null,
    options: readonly LookupOption[] | undefined,
    current: string | undefined | null,
    onPick: (v: string) => void,
    extraDisabled = false,
  ) => (
    <label className="form-row">
      <span>
        {label}
        {helpSlug && <HelpHint slug={helpSlug} small />}
        {extraDisabled && <span className="lock-hint"> 🔒</span>}
      </span>
      <select
        value={current ?? ""}
        onChange={(e) => onPick(e.target.value)}
        disabled={readOnly || extraDisabled}
      >
        <option value="">—</option>
        {(options ?? []).map((opt) => (
          <option key={opt.value} value={opt.value}>
            {optionLabel(opt)}
          </option>
        ))}
      </select>
    </label>
  );

  const renderInput = (
    label: string,
    helpSlug: string | null,
    current: string | number | undefined | null,
    onPick: (v: string) => void,
    type: "text" | "date" | "number" = "text",
    placeholder?: string,
    extraDisabled = false,
  ) => (
    <label className="form-row">
      <span>
        {label}
        {helpSlug && <HelpHint slug={helpSlug} small />}
        {extraDisabled && <span className="lock-hint"> 🔒</span>}
      </span>
      <input
        type={type}
        value={current ?? ""}
        onChange={(e) => onPick(e.target.value)}
        placeholder={placeholder}
        disabled={readOnly || extraDisabled}
      />
    </label>
  );

  const renderTextarea = (
    label: string,
    helpSlug: string | null,
    current: string | undefined | null,
    onPick: (v: string) => void,
    rows = 3,
  ) => (
    <label className="form-row">
      <span>
        {label}
        {helpSlug && <HelpHint slug={helpSlug} small />}
      </span>
      <textarea
        value={current ?? ""}
        onChange={(e) => onPick(e.target.value)}
        rows={rows}
        disabled={readOnly}
      />
    </label>
  );

  const renderMultiCsv = (
    label: string,
    helpSlug: string | null,
    current: readonly string[] | undefined,
    onPick: (next: string[]) => void,
  ) => (
    <label className="form-row">
      <span>
        {label}
        {helpSlug && <HelpHint slug={helpSlug} small />}
      </span>
      <input
        type="text"
        value={(current ?? []).join(", ")}
        placeholder="comma, separated, values"
        onChange={(e) =>
          onPick(
            e.target.value
              .split(",")
              .map((x) => x.trim())
              .filter(Boolean),
          )
        }
        disabled={readOnly}
      />
    </label>
  );

  const renderProviderSelect = (
    label: string,
    helpSlug: string,
    category: keyof ProvidersResponse,
    current: string | undefined,
    onPick: (v: string) => void,
    opts?: {
      readonly filterIds?: readonly string[] | null;
      readonly extraDisabled?: boolean;
    },
  ) => {
    let list = ((providers?.[category] as readonly ProviderInfo[]) ?? []);
    // Phase 23 — when a filter set is supplied (voice exclusivity), keep
    // only the allowed ids, but always keep the currently-selected one so
    // an already-assigned voice never silently disappears.
    if (opts?.filterIds) {
      const allowed = new Set(opts.filterIds);
      list = list.filter(
        (p) => allowed.has(p.provider_id) || p.provider_id === current,
      );
    }
    const extraDisabled = opts?.extraDisabled ?? false;
    const picked = list.find((p) => p.provider_id === current);
    return (
      <label className="form-row">
        <span>
          {label}
          <HelpHint slug={helpSlug} small />
          {extraDisabled && <span className="lock-hint"> 🔒</span>}
        </span>
        <select
          value={current ?? ""}
          onChange={(e) => onPick(e.target.value)}
          disabled={readOnly || extraDisabled}
        >
          <option value="">{t("providerStatus.selectProvider")}</option>
          {list.map((p) => (
            <option key={p.provider_id} value={p.provider_id}>
              {p.label}
            </option>
          ))}
        </select>
        {picked && (
          <ProviderStatusBadge
            status={picked.status}
            label={t(`providerStatus.${picked.status}`)}
            notes={picked.notes}
            inline
          />
        )}
      </label>
    );
  };

  // ----- render -----------------------------------------------------------

  return (
    <div className="character-form">
      {loadError && (
        <p className="muted">
          {t("characters.summary.title")}: {loadError}
        </p>
      )}

      <section>
        <h3>{t("characters.sections.identity")}</h3>
        {renderInput(t("characters.nameLabel"), null, value.profile.identity.name, (v) =>
          setIdentity({ name: v }),
        )}
        {renderInput(t("characters.displayNameLabel"), null, value.profile.identity.display_name, (v) =>
          setIdentity({ display_name: v || null }),
        )}
        {renderSelect(
          t("characters.fields.gender"),
          "character-gender",
          lookups?.gender,
          value.profile.identity.gender,
          (v) => setIdentity({ gender: v || null }),
          identityLocked,
        )}
        {renderInput(
          t("characters.fields.dateOfBirth"),
          "character-dob",
          value.profile.identity.date_of_birth,
          (v) => setIdentity({ date_of_birth: v || null }),
          "date",
          undefined,
          identityLocked,
        )}
        {renderInput(
          t("characters.fields.age"),
          null,
          value.profile.identity.age,
          (v) => setIdentity({ age: v ? Number(v) : null }),
          "number",
        )}
        {renderInput(t("characters.fields.nationality"), null, value.profile.identity.nationality, (v) =>
          setIdentity({ nationality: v || null }),
          "text",
          undefined,
          identityLocked,
        )}
        {renderSelect(
          t("characters.fields.nativeLanguage"),
          null,
          lookups?.language,
          value.profile.identity.native_language,
          (v) => setIdentity({ native_language: v || null }),
          identityLocked,
        )}
        {renderMultiCsv(
          t("characters.fields.spokenLanguages"),
          "character-spoken-languages",
          value.profile.identity.spoken_languages,
          (v) => setIdentity({ spoken_languages: v }),
        )}
        {renderSelect(
          t("characters.fields.maritalStatus"),
          null,
          lookups?.marital_status,
          value.profile.identity.marital_status,
          (v) => setIdentity({ marital_status: v || null }),
        )}
        {renderInput(t("characters.fields.placeOfBirth"), null, value.profile.identity.place_of_birth, (v) =>
          setIdentity({ place_of_birth: v || null }),
          "text",
          undefined,
          identityLocked,
        )}
        {renderInput(t("characters.fields.currentLocation"), null, value.profile.identity.current_location, (v) =>
          setIdentity({ current_location: v || null }),
        )}
        {renderSelect(
          t("characters.fields.socialStatus"),
          null,
          lookups?.social_status,
          value.profile.identity.social_status,
          (v) => setIdentity({ social_status: v || null }),
        )}
        <label className="form-row">
          <span>{t("characters.fields.isPublicPersona")}</span>
          <input
            type="checkbox"
            checked={value.profile.identity.is_public_persona ?? false}
            onChange={(e) => setIdentity({ is_public_persona: e.target.checked })}
            disabled={readOnly}
          />
        </label>
      </section>

      <section>
        <h3>{t("characters.sections.appearance")}</h3>
        {renderInput(t("characters.fields.height"), null, value.profile.appearance.height, (v) =>
          setAppearance({ height: v || null }),
        )}
        {renderInput(t("characters.fields.weightOrBuild"), null, value.profile.appearance.weight_or_build, (v) =>
          setAppearance({ weight_or_build: v || null }),
        )}
        {renderInput(t("characters.fields.skinTone"), null, value.profile.appearance.skin_tone, (v) =>
          setAppearance({ skin_tone: v || null }),
        )}
        {renderInput(t("characters.fields.hairColor"), null, value.profile.appearance.hair_color, (v) =>
          setAppearance({ hair_color: v || null }),
        )}
        {renderInput(t("characters.fields.hairStyle"), null, value.profile.appearance.hair_style, (v) =>
          setAppearance({ hair_style: v || null }),
        )}
        {renderInput(t("characters.fields.eyeColor"), null, value.profile.appearance.eye_color, (v) =>
          setAppearance({ eye_color: v || null }),
        )}
        {renderInput(t("characters.fields.faceShape"), null, value.profile.appearance.face_shape, (v) =>
          setAppearance({ face_shape: v || null }),
        )}
        {renderTextarea(t("characters.fields.distinctiveFeatures"), null, value.profile.appearance.distinctive_features, (v) =>
          setAppearance({ distinctive_features: v || null }),
        )}
        {renderInput(t("characters.fields.clothingStyle"), null, value.profile.appearance.clothing_style, (v) =>
          setAppearance({ clothing_style: v || null }),
        )}
        {renderTextarea(t("characters.fields.visualConsistencyNotes"), null, value.profile.appearance.visual_consistency_notes, (v) =>
          setAppearance({ visual_consistency_notes: v || null }),
        )}
        {renderTextarea(t("characters.fields.negativeVisualConstraints"), null, value.profile.appearance.negative_visual_constraints, (v) =>
          setAppearance({ negative_visual_constraints: v || null }),
        )}
      </section>

      <section>
        <h3>{t("characters.sections.education")}</h3>
        {renderSelect(
          t("characters.fields.educationLevel"),
          "character-education",
          lookups?.education_level,
          value.profile.education.education_level,
          (v) => setEducation({ education_level: v || null }),
          identityLocked,
        )}
        {renderInput(t("characters.fields.fieldOfStudy"), null, value.profile.education.field_of_study, (v) =>
          setEducation({ field_of_study: v || null }),
          "text",
          undefined,
          identityLocked,
        )}
        {renderMultiCsv(t("characters.fields.certifications"), null, value.profile.education.certifications, (v) =>
          setEducation({ certifications: v }),
        )}
        {renderInput(t("characters.fields.occupation"), null, value.profile.education.occupation, (v) =>
          setEducation({ occupation: v || null }),
        )}
        {renderSelect(
          t("characters.fields.seniority"),
          null,
          lookups?.professional_seniority,
          value.profile.education.professional_seniority,
          (v) => setEducation({ professional_seniority: v || null }),
        )}
        {renderInput(t("characters.fields.currentRole"), null, value.profile.education.current_role, (v) =>
          setEducation({ current_role: v || null }),
        )}
        {renderMultiCsv(t("characters.fields.previousRoles"), null, value.profile.education.previous_roles, (v) =>
          setEducation({ previous_roles: v }),
        )}
        {renderTextarea(t("characters.fields.cvSummary"), null, value.profile.education.cv_summary, (v) =>
          setEducation({ cv_summary: v || null }),
          5,
        )}
        {renderInput(t("characters.fields.industryDomain"), null, value.profile.education.industry_domain, (v) =>
          setEducation({ industry_domain: v || null }),
        )}
        {renderMultiCsv(t("characters.fields.expertise"), null, value.profile.education.expertise, (v) =>
          setEducation({ expertise: v }),
        )}
        {renderSelect(
          t("characters.fields.authorityLevel"),
          null,
          lookups?.authority_level,
          value.profile.education.authority_level,
          (v) => setEducation({ authority_level: v || null }),
        )}
        {renderTextarea(t("characters.fields.reputationNotes"), null, value.profile.education.reputation_notes, (v) =>
          setEducation({ reputation_notes: v || null }),
        )}
      </section>

      <section>
        <h3>{t("characters.sections.personality")}</h3>
        {renderSelect(
          t("characters.fields.archetype"),
          "character-archetype",
          lookups?.personality_archetype,
          value.profile.personality.archetype,
          (v) => setPersonality({ archetype: v || null }),
        )}
        {renderSelect(
          t("characters.fields.communicationStyle"),
          "character-comm-style",
          lookups?.communication_style,
          value.profile.personality.communication_style,
          (v) => setPersonality({ communication_style: v || null }),
        )}
        {renderSelect(t("characters.fields.temperament"), null, lookups?.temperament, value.profile.personality.temperament, (v) =>
          setPersonality({ temperament: v || null }),
        )}
        {renderSelect(t("characters.fields.emotionalTone"), null, lookups?.emotional_tone, value.profile.personality.emotional_tone, (v) =>
          setPersonality({ emotional_tone: v || null }),
        )}
        {renderSelect(t("characters.fields.confidenceLevel"), null, lookups?.level_scale, value.profile.personality.confidence_level, (v) =>
          setPersonality({ confidence_level: v || null }),
        )}
        {renderSelect(t("characters.fields.humorLevel"), null, lookups?.level_scale, value.profile.personality.humor_level, (v) =>
          setPersonality({ humor_level: v || null }),
        )}
        {renderSelect(t("characters.fields.formalityLevel"), null, lookups?.level_scale, value.profile.personality.formality_level, (v) =>
          setPersonality({ formality_level: v || null }),
        )}
        {renderSelect(t("characters.fields.empathyLevel"), null, lookups?.level_scale, value.profile.personality.empathy_level, (v) =>
          setPersonality({ empathy_level: v || null }),
        )}
        {renderSelect(t("characters.fields.assertivenessLevel"), null, lookups?.level_scale, value.profile.personality.assertiveness_level, (v) =>
          setPersonality({ assertiveness_level: v || null }),
        )}
        {renderSelect(t("characters.fields.patienceLevel"), null, lookups?.level_scale, value.profile.personality.patience_level, (v) =>
          setPersonality({ patience_level: v || null }),
        )}
        {renderTextarea(t("characters.fields.moralValues"), null, value.profile.personality.moral_values, (v) =>
          setPersonality({ moral_values: v || null }),
        )}
        {renderTextarea(t("characters.fields.fears"), null, value.profile.personality.fears, (v) =>
          setPersonality({ fears: v || null }),
        )}
        {renderTextarea(t("characters.fields.motivations"), null, value.profile.personality.motivations, (v) =>
          setPersonality({ motivations: v || null }),
        )}
        {renderTextarea(t("characters.fields.goals"), null, value.profile.personality.goals, (v) =>
          setPersonality({ goals: v || null }),
        )}
        {renderSelect(t("characters.fields.conflictStyle"), null, lookups?.conflict_style, value.profile.personality.conflict_style, (v) =>
          setPersonality({ conflict_style: v || null }),
        )}
        {renderSelect(t("characters.fields.decisionStyle"), null, lookups?.decision_style, value.profile.personality.decision_style, (v) =>
          setPersonality({ decision_style: v || null }),
        )}
        {renderSelect(t("characters.fields.narrativeRole"), null, lookups?.narrative_role, value.profile.personality.narrative_role, (v) =>
          setPersonality({ narrative_role: v || null }),
        )}
      </section>

      <section>
        <h3>{t("characters.sections.voice")}</h3>
        {renderSelect(t("characters.fields.voiceLanguage"), null, lookups?.language, value.profile.voice.preferred_language, (v) =>
          setVoice({ preferred_language: v || null }),
        )}
        {renderInput(t("characters.fields.accent"), null, value.profile.voice.accent, (v) =>
          setVoice({ accent: v || null }),
        )}
        {renderSelect(t("characters.fields.voiceGender"), null, lookups?.voice_gender, value.profile.voice.voice_gender, (v) =>
          setVoice({ voice_gender: v || null }),
        )}
        {renderSelect(t("characters.fields.voiceAge"), null, lookups?.voice_age, value.profile.voice.voice_age, (v) =>
          setVoice({ voice_age: v || null }),
        )}
        {renderSelect(t("characters.fields.speakingSpeed"), null, lookups?.speaking_speed, value.profile.voice.speaking_speed, (v) =>
          setVoice({ speaking_speed: v || null }),
        )}
        {renderSelect(t("characters.fields.pitch"), null, lookups?.pitch, value.profile.voice.pitch, (v) =>
          setVoice({ pitch: v || null }),
        )}
        {renderSelect(t("characters.fields.tone"), null, lookups?.tone, value.profile.voice.tone, (v) =>
          setVoice({ tone: v || null }),
        )}
        {renderProviderSelect(
          t("characters.fields.ttsProvider"),
          "character-tts-provider",
          "tts",
          value.profile.voice.preferred_tts_provider_id ?? value.default_voice_provider_id,
          (v) => {
            setVoice({ preferred_tts_provider_id: v || null });
            onChange({ ...value, default_voice_provider_id: v });
          },
          { filterIds: availableVoices, extraDisabled: identityLocked },
        )}
        {renderInput(t("characters.fields.f5ttsProfile"), null, value.profile.voice.f5tts_profile, (v) =>
          setVoice({ f5tts_profile: v || null }),
        )}
        {renderInput(t("characters.fields.voiceSampleLibrary"), null, value.profile.voice.voice_sample_library_ref, (v) =>
          setVoice({ voice_sample_library_ref: v || null }),
        )}
      </section>

      <section>
        <h3>{t("characters.sections.script")}</h3>
        {renderSelect(t("characters.fields.defaultRole"), null, lookups?.narrative_role, value.profile.script_behaviour.default_role_in_videos, (v) =>
          setBehaviour({ default_role_in_videos: v || null }),
        )}
        {renderInput(t("characters.fields.defaultSpeakingDuration"), null, value.profile.script_behaviour.default_speaking_duration_seconds, (v) =>
          setBehaviour({ default_speaking_duration_seconds: v ? Number(v) : null }),
          "number",
        )}
        {renderSelect(t("characters.fields.defaultFraming"), null, lookups?.camera_framing, value.profile.script_behaviour.default_camera_framing, (v) =>
          setBehaviour({ default_camera_framing: v || null }),
        )}
        {renderSelect(t("characters.fields.defaultMood"), null, lookups?.mood, value.profile.script_behaviour.default_mood, (v) =>
          setBehaviour({ default_mood: v || null }),
        )}
        {renderInput(t("characters.fields.defaultBackground"), null, value.profile.script_behaviour.default_background, (v) =>
          setBehaviour({ default_background: v || null }),
        )}
        {renderInput(t("characters.fields.defaultExpertise"), null, value.profile.script_behaviour.default_topic_expertise, (v) =>
          setBehaviour({ default_topic_expertise: v || null }),
        )}
        {renderMultiCsv(t("characters.fields.allowedTopics"), null, value.profile.script_behaviour.allowed_topics, (v) =>
          setBehaviour({ allowed_topics: v }),
        )}
        {renderMultiCsv(t("characters.fields.blockedTopics"), "character-blocked-topics", value.profile.script_behaviour.blocked_topics, (v) =>
          setBehaviour({ blocked_topics: v }),
        )}
        {renderTextarea(t("characters.fields.safetyNotes"), null, value.profile.script_behaviour.safety_notes, (v) =>
          setBehaviour({ safety_notes: v || null }),
        )}
        {renderTextarea(t("characters.fields.promptStyleNotes"), null, value.profile.script_behaviour.prompt_style_notes, (v) =>
          setBehaviour({ prompt_style_notes: v || null }),
        )}
        {renderTextarea(t("characters.fields.scriptGenerationNotes"), null, value.profile.script_behaviour.script_generation_notes, (v) =>
          setBehaviour({ script_generation_notes: v || null }),
        )}
      </section>

      <section>
        <h3>{t("characters.sections.settings")}</h3>
        {renderSelect(
          t("characters.statusLabel"),
          null,
          lookups?.character_status,
          value.status,
          (v) => onChange({ ...value, status: (v || "editing") as CharacterStatus }),
        )}
        {renderSelect(
          t("characters.languageLabel"),
          null,
          lookups?.language,
          value.default_language,
          (v) => onChange({ ...value, default_language: v }),
        )}
        {renderProviderSelect(
          t("characters.imageProviderLabel"),
          "character-image-provider",
          "image_generator",
          value.default_image_provider_id,
          (v) => onChange({ ...value, default_image_provider_id: v }),
        )}
      </section>
    </div>
  );
}
