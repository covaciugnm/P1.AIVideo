"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import * as logBus from "@/lib/log-bus";
import type {
  CreateJobFromInputsBody,
  FaceMode,
  ProviderInfo,
  ProvidersResponse,
  UIOptions,
  UploadAudioResponse,
  UploadImageResponse,
  VoiceMode,
} from "@/lib/types";

import { useT } from "@/lib/i18n/LanguageContext";
import { localizeApiDetail } from "@/lib/i18n/formatters";

import { AudioPreview } from "./AudioPreview";
import { ErrorMessage } from "./ErrorMessage";
import { HelpHint } from "./HelpHint";
import { ProviderStatusBadge } from "./ProviderStatusBadge";
import { useSettings } from "./SettingsContext";
import { UploadCard } from "./UploadCard";
import styles from "./CreateJobForm.module.css";
import {
  type CharacterSummary,
  listCharacters,
} from "@/lib/characters";

interface CreateJobFormProps {
  readonly uiOptions: UIOptions;
}

export function CreateJobForm({ uiOptions }: CreateJobFormProps) {
  const t = useT();
  const router = useRouter();
  const { settings } = useSettings();
  const [brief, setBrief] = useState("");
  const [duration, setDuration] = useState<number>(
    settings.defaultTargetDurationSeconds || uiOptions.duration_bounds.default_seconds,
  );
  const [voiceMode, setVoiceMode] = useState<VoiceMode>(
    settings.defaultVoiceMode,
  );
  const [scriptText, setScriptText] = useState("");
  // Per-job provider selection. Initialized from Settings defaults but
  // operator-editable per job.
  const [llmProvider, setLlmProvider] = useState<string | null>(
    settings.defaultLlmProvider,
  );
  const [ttsProvider, setTtsProvider] = useState<string | null>(
    settings.defaultTtsProvider,
  );
  const [videoProvider, setVideoProvider] = useState<string | null>(
    settings.defaultVideoProvider,
  );
  // Phase 6D — audio + image processor selection.
  const [audioProcessor, setAudioProcessor] = useState<string | null>(null);
  const [imageProcessor, setImageProcessor] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [ttsBusy, setTtsBusy] = useState(false);
  const [ttsStatus, setTtsStatus] = useState<string | null>(null);
  // Phase 8G-2 — capture the generated TTS artifact so we can render
  // an inline preview after a successful Generate Audio click.
  const [ttsArtifact, setTtsArtifact] = useState<{
    readonly artifact_id: string;
    readonly provider_id: string;
    readonly voice_id: string;
    readonly mime_type: string;
    readonly size_bytes: number;
    readonly duration_seconds: number;
    readonly sample_rate: number;
    readonly channels: number;
  } | null>(null);
  const ttsAbortRef = useRef<AbortController | null>(null);
  // Phase 5B — script generation preview.
  const [scriptBusy, setScriptBusy] = useState(false);
  const [scriptStatus, setScriptStatus] = useState<string | null>(null);
  const scriptAbortRef = useRef<AbortController | null>(null);
  // Phase 5C — fit-check result for uploaded audio.
  const [audioFit, setAudioFit] = useState<{
    fit_status: string;
    delta_seconds: number | null;
    recommendation: string;
    audio_duration_seconds: number | null;
  } | null>(null);
  // Phase 12 — character binding for this job. Dropdown sourced
  // dynamically from /api/v1/characters (no hardcoded array).
  const [characters, setCharacters] = useState<readonly CharacterSummary[]>([]);
  const [characterId, setCharacterId] = useState<string>("");
  const [characterListError, setCharacterListError] = useState<string | null>(null);
  const reloadCharacters = async () => {
    try {
      const r = await listCharacters();
      setCharacters(r.items.filter((c) => c.status === "active"));
      setCharacterListError(null);
    } catch (err) {
      setCharacterListError((err as Error).message);
    }
  };
  useEffect(() => {
    void reloadCharacters();
  }, []);
  const selectedCharacter = characters.find((c) => c.id === characterId) ?? null;

  // Phase 17 — prefill from URL query params:
  //   ?character_id=...&brief=... → pre-populate the form when the user
  //   clicks "Generate video with this image" from the character image
  //   library. Runs once at mount, only when fields are empty so we
  //   don't clobber operator edits.
  const searchParams = useSearchParams();
  const prefillAppliedRef = useRef(false);
  useEffect(() => {
    if (prefillAppliedRef.current) return;
    if (!searchParams) return;
    const cid = searchParams.get("character_id");
    const brf = searchParams.get("brief");
    let did = false;
    if (cid && !characterId) {
      setCharacterId(cid);
      did = true;
    }
    if (brf && !brief) {
      setBrief(brf);
      did = true;
    }
    if (did) {
      prefillAppliedRef.current = true;
      logBus.emit({
        source: "frontend", level: "info",
        message: `create-job prefilled from URL (character=${cid}, brief=${brf?.slice(0, 60)})`,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const p = await api.getProviders(controller.signal);
        setProviders(p);
      } catch {
        // Providers panel is optional; the form still works.
      }
    })();
    return () => controller.abort();
  }, []);

  const handleScriptGenerate = async () => {
    if (!brief.trim()) {
      setScriptStatus(t("badges.fillBriefFirst"));
      return;
    }
    scriptAbortRef.current?.abort();
    const controller = new AbortController();
    scriptAbortRef.current = controller;
    setScriptBusy(true);
    setScriptStatus(t("createJob.generateScriptBusy"));
    logBus.emit({
      source: "frontend",
      level: "info",
      message: `script-generate start (provider=${llmProvider ?? "template"})`,
      meta: { provider_id: llmProvider ?? "template" },
    });
    const res = await api.generateScript(
      {
        brief: brief.trim(),
        target_duration_seconds: duration,
        script_text: scriptText.trim() || null,
        provider_id: llmProvider ?? "template",
      },
      controller.signal,
    );
    setScriptBusy(false);
    if (!res.ok) {
      setScriptStatus(
        `${res.error.code.replace(/_/g, " ")}: ${res.error.message}`,
      );
      logBus.emit({
        source: "frontend",
        level: res.httpStatus === 503 ? "warning" : "error",
        message: `script-generate ${res.error.code}`,
        meta: { code: res.error.code, status: res.httpStatus },
      });
      return;
    }
    setScriptText(res.value.full_script);
    setScriptStatus(
      t("createJob.scriptGeneratedStatus", {
        provider: res.value.provider_id,
        model: res.value.model,
        duration: res.value.estimated_duration_seconds.toFixed(1),
      }),
    );
    logBus.emit({
      source: "frontend",
      level: "success",
      message: `script-generate succeeded (provider=${res.value.provider_id})`,
      meta: { provider_id: res.value.provider_id, model: res.value.model },
    });
  };

  const runFitCheck = async (artifactId: string) => {
    try {
      const fit = await api.audioFitCheck({
        audio_artifact_id: artifactId,
        target_duration_seconds: duration,
      });
      setAudioFit({
        fit_status: fit.fit_status,
        delta_seconds: fit.delta_seconds,
        recommendation: fit.recommendation,
        audio_duration_seconds: fit.audio_duration_seconds,
      });
      logBus.emit({
        source: "frontend",
        level: fit.fit_status === "ok" ? "info" : "warning",
        message: `audio fit ${fit.fit_status} (Δ${fit.delta_seconds}s)`,
        meta: {
          fit_status: fit.fit_status,
          recommendation: fit.recommendation,
        },
      });
    } catch {
      // Fit-check is opportunistic — silent failure is acceptable.
      setAudioFit(null);
    }
  };

  const handleTtsGenerate = async () => {
    if (!scriptText.trim()) return;
    ttsAbortRef.current?.abort();
    const controller = new AbortController();
    ttsAbortRef.current = controller;
    setTtsBusy(true);
    setTtsStatus(t("createJob.generateAudioBusy"));
    logBus.emit({
      source: "frontend",
      level: "info",
      message: `tts-generate start (provider=${ttsProvider ?? "default"})`,
      meta: { provider_id: ttsProvider ?? "default" },
    });
    const res = await api.generateTts(
      {
        script_text: scriptText.trim(),
        tts_provider_id: ttsProvider ?? "piper",
      },
      controller.signal,
    );
    setTtsBusy(false);
    if (!res.ok) {
      // Phase 8G-2 + Phase 10A-1 — operator-friendly copy keyed on both
      // the error code AND the selected provider, so F5TTS-Ro shows
      // Romanian-specific guidance instead of Piper-only instructions.
      const isF5 = (ttsProvider ?? "piper") === "f5tts_ro";
      const niceMsg = isF5
        ? t(`niceErrors.f5_${res.error.code.replace("tts_", "")}` as any)
        : t(`niceErrors.piper_${res.error.code.replace("tts_", "")}` as any);

      // Fallback to raw message if key lookup fails (path missing in Dictionary).
      const finalMsg = niceMsg.includes("niceErrors.")
        ? res.error.message
        : niceMsg;

      setTtsStatus(finalMsg);
      setTtsArtifact(null);
      logBus.emit({
        source: "frontend",
        level: res.httpStatus === 503 ? "warning" : "error",
        message: `tts-generate ${res.error.code}`,
        meta: { code: res.error.code, status: res.httpStatus },
      });
    } else {
      const v = res.value;
      // Phase 8G-2 — capture the generated artifact + render preview.
      setTtsArtifact({
        artifact_id: v.artifact_id,
        provider_id: v.provider_id,
        voice_id: v.voice_id,
        mime_type: v.mime_type,
        size_bytes: v.size_bytes,
        duration_seconds: v.duration_seconds,
        sample_rate: v.sample_rate,
        channels: v.channels,
      });
      setTtsStatus(
        t("createJob.ttsGeneratedStatus", {
          duration: v.duration_seconds.toFixed(2),
          rate: v.sample_rate,
          channels: v.channels,
          size: (v.size_bytes / 1024).toFixed(1),
        }),
      );
      logBus.emit({
        source: "frontend",
        level: "success",
        message: "tts-generate succeeded",
        meta: {
          artifact_id: v.artifact_id,
          provider_id: v.provider_id,
          duration_seconds: v.duration_seconds,
        },
      });
    }
  };
  const [audioArtifact, setAudioArtifact] = useState<UploadAudioResponse | null>(
    null,
  );
  const [audioConsent, setAudioConsent] = useState(false);
  const [audioOwned, setAudioOwned] = useState(false);

  const [useFace, setUseFace] = useState(false);
  const [imageArtifact, setImageArtifact] = useState<UploadImageResponse | null>(
    null,
  );
  const [imageConsent, setImageConsent] = useState(false);
  const [imageSynthetic, setImageSynthetic] = useState(false);

  // Phase 11A — language + subtitle state. Default video language
  // tracks the current UI language so a Romanian operator gets RO out
  // of the box without an extra click.
  const [videoLanguage, setVideoLanguage] = useState<string>("ro");
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(false);
  const [subtitleLangsRo, setSubtitleLangsRo] = useState(true);
  const [subtitleLangsEn, setSubtitleLangsEn] = useState(false);
  const [subtitleFormat, setSubtitleFormat] = useState<"srt" | "vtt">("srt");
  const [subtitleBurnIn, setSubtitleBurnIn] = useState(false);

  const [syntheticPerson, setSyntheticPerson] = useState(false);
  const [consent, setConsent] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const durMin = uiOptions.duration_bounds.min_seconds;
  const durMax = uiOptions.duration_bounds.max_seconds;
  const audioMax = uiOptions.upload_limits.audio_max_bytes;
  const imageMax = uiOptions.upload_limits.image_max_bytes;
  const audioExts = uiOptions.upload_limits.accepted_audio_extensions;
  const imageExts = uiOptions.upload_limits.accepted_image_extensions;
  const scriptMaxChars = uiOptions.upload_limits.script_text_max_chars;

  const canSubmit =
    brief.trim().length > 0 &&
    // Phase 17 — character REQUIRED. Videos must be linked to a character;
    // anonymous generation is no longer allowed from the dashboard.
    characterId.length > 0 &&
    duration >= durMin &&
    duration <= durMax &&
    syntheticPerson &&
    consent &&
    (voiceMode === "tts"
      ? scriptText.trim().length > 0
      : audioArtifact !== null && audioConsent && audioOwned) &&
    (!useFace ||
      (imageArtifact !== null && imageConsent && imageSynthetic)) &&
    !submitting;

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);

    const faceMode: FaceMode | null = useFace ? "provided_image" : null;

    const body: CreateJobFromInputsBody = {
      brief: brief.trim(),
      target_duration_seconds: duration,
      synthetic_person_confirmed: syntheticPerson,
      consent_confirmed: consent,
      watermark_required: true,
      c2pa_required: true,
      voice_mode: voiceMode,
      face_mode: faceMode,
      script_text: voiceMode === "tts" ? scriptText.trim() : null,
      audio_artifact_id:
        voiceMode === "provided_audio" ? audioArtifact?.artifact_id ?? null : null,
      audio_consent_confirmed:
        voiceMode === "provided_audio" ? audioConsent : false,
      audio_synthetic_or_owned:
        voiceMode === "provided_audio" ? audioOwned : false,
      image_artifact_id: useFace ? imageArtifact?.artifact_id ?? null : null,
      image_consent_confirmed: useFace ? imageConsent : false,
      image_synthetic_person_confirmed: useFace ? imageSynthetic : false,
      provider_selection:
        llmProvider ||
        ttsProvider ||
        videoProvider ||
        audioProcessor ||
        imageProcessor
          ? {
              script_provider_id: llmProvider,
              tts_provider_id: ttsProvider,
              video_provider_id: videoProvider,
              audio_processor_id: audioProcessor,
              image_processor_id: imageProcessor,
            }
          : null,
      // Phase 11A — language + subtitle metadata.
      video_language: videoLanguage,
      subtitle_enabled: subtitlesEnabled,
      subtitle_languages: subtitlesEnabled
        ? [
            ...(subtitleLangsRo ? ["ro"] : []),
            ...(subtitleLangsEn ? ["en"] : []),
          ]
        : null,
      subtitle_format: subtitleFormat,
      subtitle_burn_in: subtitleBurnIn,
      // Phase 12 — optional persona binding.
      character_id: characterId || null,
    };

    logBus.emit({
      source: "frontend",
      level: "info",
      message: "create-job submitted",
      meta: {
        voice_mode: body.voice_mode,
        face_mode: body.face_mode ?? null,
        target_duration_seconds: body.target_duration_seconds,
      },
    });

    try {
      const job = await api.createJobFromInputs(body);
      logBus.emit({
        source: "frontend",
        level: "success",
        message: `create-job succeeded → ${job.id}`,
        meta: { jobId: job.id, status: job.status },
      });
      router.push(`/jobs/${job.id}`);
    } catch (err) {
      const raw = err instanceof ApiError ? err.detail : String(err);
      const msg = localizeApiDetail(t, err);
      setError(msg);
      logBus.emit({
        source: "frontend",
        level: "error",
        message: "create-job failed",
        meta: { error: msg, raw },
      });
      setSubmitting(false);
    }
  };

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <section
        className="card"
        data-testid="character-section"
        style={{
          borderColor: characterId ? undefined : "var(--danger, #f06a6a)",
          borderWidth: 2, borderStyle: "solid",
        }}
      >
        <h2>
          {t("videoCharacter.sectionTitle")} <HelpHint slug="video-character" small />
          {!characterId && (
            <span style={{ marginLeft: 8, color: "var(--danger, #f06a6a)", fontSize: "0.7em" }}>
              ⚠ {t("videoCharacter.requiredBadge")}
            </span>
          )}
        </h2>
        <p className="muted" style={{ fontSize: 12 }}>{t("videoCharacter.helpHint")}</p>
        <div className="field">
          <select
            value={characterId}
            onChange={(e) => setCharacterId(e.target.value)}
            data-testid="character-dropdown"
            required
          >
            <option value="">— {t("videoCharacter.pickRequired")} —</option>
            {characters.map((c) => (
              <option key={c.id} value={c.id}>
                {(c.display_name || c.name)} · {c.default_language ?? "—"}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void reloadCharacters()}
            style={{ marginLeft: 8 }}
          >
            {t("videoCharacter.refreshList")}
          </button>
          {characterListError && (
            <p style={{ color: "var(--danger)", fontSize: 12 }}>
              {t("videoCharacter.loadFailed", { detail: characterListError })}
            </p>
          )}
        </div>
        {selectedCharacter && (
          <div className="card" style={{ marginTop: 8, padding: 8 }}>
            <strong>{t("characters.summary.title")}: {selectedCharacter.display_name || selectedCharacter.name}</strong>
            <div className="muted" style={{ fontSize: 12 }}>
              {t("characters.summary.language")}: {selectedCharacter.default_language ?? t("characters.summary.none")}
              {" · "}
              {t("characters.summary.voiceProvider")}: {selectedCharacter.default_voice_provider_id ?? t("characters.summary.none")}
              {" · "}
              {t("characters.summary.imageProvider")}: {selectedCharacter.default_image_provider_id ?? t("characters.summary.none")}
              {" · "}
              {t("characters.summary.reference")}: {selectedCharacter.main_reference_image_id ? "✓" : t("characters.summary.none")}
            </div>
          </div>
        )}
      </section>
      <section className="card">
        <h2>1. {t("createJob.sectionBrief").replace(/^\d+\.\s*/, "")} <HelpHint slug="create-job" small /></h2>
        <div className="field">
          <label htmlFor="brief">{t("createJob.briefLabel")}</label>
          <textarea
            id="brief"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            maxLength={2000}
            placeholder={t("createJob.briefPlaceholder")}
            required
          />
          <span className={styles.muted}>{brief.length} / 2000</span>
        </div>
        <div className="field">
          <label htmlFor="duration">{t("createJob.targetDuration")}</label>
          <input
            id="duration"
            type="number"
            min={durMin}
            max={durMax}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
          />
          <span className={styles.muted}>
            {t("createJob.durationBetween", { min: durMin, max: durMax })}
          </span>
        </div>
      </section>

      <section className="card">
        <h2>2. {t("createJob.sectionVoice").replace(/^\d+\.\s*/, "")} <HelpHint slug="piper" small /></h2>
        <div className="field">
          <label>{t("createJob.voiceMode")}</label>
          <div className="row">
            {uiOptions.voice_modes.map((vm) => (
              <label key={vm.value} className={styles.radio}>
                <input
                  type="radio"
                  name="voice_mode"
                  value={vm.value}
                  checked={voiceMode === vm.value}
                  onChange={() => setVoiceMode(vm.value)}
                />
                <span>
                  {vm.value === "tts" ? t("createJob.voiceTts") : t("createJob.voiceProvided")}
                </span>
              </label>
            ))}
          </div>
        </div>
        {voiceMode === "tts" ? (
          <div className="field">
            <label htmlFor="script">{t("createJob.scriptText")}</label>
            <textarea
              id="script"
              value={scriptText}
              onChange={(e) => setScriptText(e.target.value)}
              maxLength={scriptMaxChars}
              placeholder={t("createJob.scriptPlaceholder")}
              required
            />
            <span className={styles.muted}>
              {t("createJob.scriptCounter", { n: scriptText.length, max: scriptMaxChars })}
            </span>
            <div className={styles.ttsRow}>
              <button
                type="button"
                className="btn"
                onClick={handleScriptGenerate}
                disabled={scriptBusy || brief.trim().length === 0}
                title={t("createJob.generateScript")}
              >
                {scriptBusy ? t("createJob.generateScriptBusy") : t("createJob.generateScript")}
              </button>
              <button
                type="button"
                className="btn"
                onClick={handleTtsGenerate}
                disabled={ttsBusy || scriptText.trim().length === 0}
              >
                {ttsBusy ? t("createJob.generateAudioBusy") : t("createJob.generateAudio")}
              </button>
              {scriptStatus && (
                <span className={styles.ttsStatus}>{scriptStatus}</span>
              )}
              {ttsStatus && (
                <span className={styles.ttsStatus}>{ttsStatus}</span>
              )}
            </div>
            {ttsArtifact && (
              <AudioPreview
                src={{ kind: "artifact", artifactId: ttsArtifact.artifact_id }}
                label={t("createJob.ttsPreviewLabel", { provider: ttsArtifact.provider_id, voice: ttsArtifact.voice_id })}
              />
            )}
          </div>
        ) : (
          <>
            <UploadCard
              kind="audio"
              title={t("createJob.providedAudioTitle")}
              help={t("uploads.audioHelp")}
              acceptExtensions={audioExts}
              maxBytes={audioMax}
              onUploaded={(r) => {
                const audio = r as UploadAudioResponse;
                setAudioArtifact(audio);
                void runFitCheck(audio.artifact_id);
              }}
              currentArtifactId={audioArtifact?.artifact_id ?? null}
            />
            {audioArtifact && (
              <AudioPreview
                src={{ kind: "artifact", artifactId: audioArtifact.artifact_id }}
                label={t("createJob.providedAudioTitle")}
              />
            )}
            {audioFit && (
              <AudioFitStrip
                fitStatus={audioFit.fit_status}
                deltaSeconds={audioFit.delta_seconds}
                recommendation={audioFit.recommendation}
                audioDurationSeconds={audioFit.audio_duration_seconds}
                target={duration}
              />
            )}
            <div className={styles.consentBlock}>
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={audioConsent}
                  onChange={(e) => setAudioConsent(e.target.checked)}
                />
                <span>{t("createJob.audioConsent")}</span>
              </label>
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={audioOwned}
                  onChange={(e) => setAudioOwned(e.target.checked)}
                />
                <span>{t("createJob.audioOwned")}</span>
              </label>
            </div>
          </>
        )}
      </section>

      <section className="card">
        <h2>{t("createJob.sectionProviders")} <HelpHint slug="provider-selection" small /></h2>
        <p className={styles.muted}>{t("providersSection.intro")}</p>
        <ProviderField
          label={t("createJob.scriptProvider")}
          value={llmProvider}
          onChange={setLlmProvider}
          providers={providers?.llm ?? []}
          defaultFromSettings={settings.defaultLlmProvider}
        />
        <ProviderField
          label={t("createJob.ttsProvider")}
          value={ttsProvider}
          onChange={setTtsProvider}
          providers={providers?.tts ?? []}
          defaultFromSettings={settings.defaultTtsProvider}
        />
        <ProviderField
          label={t("createJob.videoProvider")}
          value={videoProvider}
          onChange={setVideoProvider}
          providers={providers?.video_generator ?? []}
          defaultFromSettings={settings.defaultVideoProvider}
        />
        <ProviderField
          label={t("createJob.audioProcessor")}
          value={audioProcessor}
          onChange={setAudioProcessor}
          providers={providers?.audio_processor ?? []}
        />
        <ProviderField
          label={t("createJob.imageProcessor")}
          value={imageProcessor}
          onChange={setImageProcessor}
          providers={providers?.image_processor ?? []}
        />
      </section>

      <section className="card">
        <h2>{t("createJob.sectionFace")} <HelpHint slug="image-upload" small /></h2>
        <label className={styles.checkbox}>
          <input
            type="checkbox"
            checked={useFace}
            onChange={(e) => setUseFace(e.target.checked)}
          />
          <span>{t("createJob.useProvidedImage")}</span>
        </label>
        {useFace && (
          <>
            <UploadCard
              kind="image"
              title={t("createJob.providedImageTitle")}
              help={t("uploads.imageHelp")}
              acceptExtensions={imageExts}
              maxBytes={imageMax}
              onUploaded={(r) => setImageArtifact(r as UploadImageResponse)}
              currentArtifactId={imageArtifact?.artifact_id ?? null}
            />
            {imageArtifact && (
              <ImagePreview
                artifactId={imageArtifact.artifact_id}
                width={imageArtifact.width}
                height={imageArtifact.height}
                mimeType={imageArtifact.mime_type}
              />
            )}
            <div className={styles.consentBlock}>
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={imageConsent}
                  onChange={(e) => setImageConsent(e.target.checked)}
                />
                <span>{t("createJob.imageConsent")}</span>
              </label>
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={imageSynthetic}
                  onChange={(e) => setImageSynthetic(e.target.checked)}
                />
                <span>{t("createJob.imageSynthetic")}</span>
              </label>
            </div>
          </>
        )}
      </section>

      <section className="card">
        <h2>{t("createJob.sectionLanguage")} <HelpHint slug="subtitles" small /></h2>
        <p className="muted" style={{ marginTop: -8, marginBottom: 12 }}>
          {t("createJob.languageIntro")}
        </p>
        <div className="field">
          <label htmlFor="video-language">{t("createJob.videoLanguage")}</label>
          <select
            id="video-language"
            value={videoLanguage}
            onChange={(e) => setVideoLanguage(e.target.value)}
          >
            <option value="ro">{t("common.romanian")}</option>
            <option value="en">{t("common.english")}</option>
          </select>
        </div>
        <label className={styles.checkbox}>
          <input
            type="checkbox"
            checked={subtitlesEnabled}
            onChange={(e) => setSubtitlesEnabled(e.target.checked)}
          />
          <span>{t("createJob.enableSubtitles")}</span>
        </label>
        {subtitlesEnabled && (
          <>
            <div className="field" style={{ marginTop: 8 }}>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                {t("createJob.subtitleLanguages")}
              </span>
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={subtitleLangsRo}
                  onChange={(e) => setSubtitleLangsRo(e.target.checked)}
                />
                <span>{t("common.romanian")}</span>
              </label>
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={subtitleLangsEn}
                  onChange={(e) => setSubtitleLangsEn(e.target.checked)}
                />
                <span>{t("common.english")}</span>
              </label>
            </div>
            <div className="field">
              <label htmlFor="subtitle-format">{t("createJob.subtitleFormat")}</label>
              <select
                id="subtitle-format"
                value={subtitleFormat}
                onChange={(e) =>
                  setSubtitleFormat(e.target.value as "srt" | "vtt")
                }
              >
                <option value="srt">{t("providerSelection.subtitleFormatSrt")}</option>
                <option value="vtt">{t("providerSelection.subtitleFormatVtt")}</option>
              </select>
            </div>
            <label className={styles.checkbox}>
              <input
                type="checkbox"
                checked={subtitleBurnIn}
                onChange={(e) => setSubtitleBurnIn(e.target.checked)}
              />
              <span>
                {t("createJob.burnSubtitles")}{" "}
                <em style={{ color: "var(--warn)" }}>
                  ({t("createJob.burnNotImplemented")})
                </em>
              </span>
            </label>
          </>
        )}
      </section>

      <section className="card">
        <h2>{t("createJob.sectionCompliance")} <HelpHint slug="create-job" small /></h2>
        <div className="compliance-banner">{t("createJob.complianceBanner")}</div>
        <div className={styles.consentBlock}>
          <label className={styles.checkbox}>
            <input
              type="checkbox"
              checked={syntheticPerson}
              onChange={(e) => setSyntheticPerson(e.target.checked)}
            />
            <span>{t("createJob.syntheticConfirm")}</span>
          </label>
          <label className={styles.checkbox}>
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>{t("createJob.consentConfirm")}</span>
          </label>
        </div>
      </section>

      {error && <ErrorMessage message={error} />}

      <div className={styles.actions}>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={!canSubmit}
        >
          {submitting ? t("createJob.submitting") : t("createJob.submit")}
        </button>
      </div>
    </form>
  );
}

interface ProviderFieldProps {
  readonly label: string;
  readonly value: string | null;
  readonly onChange: (v: string | null) => void;
  readonly providers: readonly ProviderInfo[];
  readonly defaultFromSettings?: string | null;
}

function ProviderField({
  label,
  value,
  onChange,
  providers,
  defaultFromSettings,
}: ProviderFieldProps) {
  const t = useT();
  const selected = providers.find((p) => p.provider_id === value);
  const warn =
    selected && selected.status !== "available" && selected.status !== "configured";
  const defaultLabel = defaultFromSettings
    ? t("createJob.providerInheritWithName").replace("{name}", defaultFromSettings)
    : t("createJob.providerInherit");
  return (
    <div className="field">
      <label>{label}</label>
      <select
        className={styles.select}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">{defaultLabel}</option>
        {providers.map((p) => (
          <option key={p.provider_id} value={p.provider_id}>
            {p.label} ({t(`providerStatuses.${p.status}` as any)})
            {p.requires_gpu ? " · GPU" : ""}
            {p.requires_network ? ` · ${t("common.search").replace("Search", "network") === "network" ? "network" : "rețea"}` : ""}
            {p.is_custom ? ` · ${t("common.stub")}` : ""}
          </option>
        ))}
      </select>
      {selected && (
        <span className={styles.providerBadges}>
          {selected.requires_gpu && (
            <span className={styles.badgeGpu} title={t("badges.gpuRequired")}>
              {t("badges.gpuRequired")}
            </span>
          )}
          {selected.requires_network && (
            <span className={styles.badgeNet} title={t("badges.requiresNetwork")}>
              {t("badges.requiresNetwork")}
            </span>
          )}
          {selected.requires_model_files && (
            <span className={styles.badgeAssets} title={t("badges.requiresModelFiles")}>
              {t("badges.requiresModelFiles")}
            </span>
          )}
          {selected.is_custom && (
            <span className={styles.badgeCustom} title={t("badges.customMetadataOnly")}>
              {t("badges.customMetadataOnly")}
            </span>
          )}
        </span>
      )}
      {warn && (
        <span className={styles.providerWarn}>
          ⚠ {t("providerSelection.warningPrefix")}{" "}
          <strong>{selected.label}</strong>{" "}
          <code>{t(`providerStatuses.${selected.status}` as any)}</code>
          {selected.notes ? ` — ${selected.notes}.` : ""}{" "}
          {t("providerSelection.warningSuffixCleanError")}
        </span>
      )}
    </div>
  );
}

interface ImagePreviewProps {
  readonly artifactId: string;
  readonly width: number;
  readonly height: number;
  readonly mimeType: string;
}

interface AudioFitStripProps {
  readonly fitStatus: string;
  readonly deltaSeconds: number | null;
  readonly recommendation: string;
  readonly audioDurationSeconds: number | null;
  readonly target: number;
}

function AudioFitStrip({
  fitStatus,
  deltaSeconds,
  recommendation,
  audioDurationSeconds,
  target,
}: AudioFitStripProps) {
  const t = useT();
  const tone =
    fitStatus === "ok"
      ? styles.fitOk
      : fitStatus === "missing_audio"
        ? styles.fitMuted
        : styles.fitWarn;
  const deltaLabel =
    deltaSeconds === null
      ? "—"
      : `${deltaSeconds > 0 ? "+" : ""}${deltaSeconds.toFixed(2)}s`;
  return (
    <div className={`${styles.fitStrip} ${tone}`}>
      <span className={styles.fitLabel}>
        {t("runtime.audioFitStatus", { status: t(`runtime.audioFit${fitStatus.replace(/_([a-z])/g, (_, l) => l.toUpperCase()).replace(/^[a-z]/, (l) => l.toUpperCase())}` as any) })}
      </span>
      <span className={styles.fitMeta}>
        {t("runtime.audioFitMeta", {
          target,
          audio: audioDurationSeconds !== null ? audioDurationSeconds.toFixed(2) : "—",
          delta: deltaLabel
        })}
      </span>
      {fitStatus !== "ok" && (
        <span className={styles.fitRec}>
          → {t(`runtime.audioFitRec${recommendation.replace(/_([a-z])/g, (_, l) => l.toUpperCase()).replace(/^[a-z]/, (l) => l.toUpperCase())}` as any)}
        </span>
      )}
    </div>
  );
}

function ImagePreview({ artifactId, width, height, mimeType }: ImagePreviewProps) {
  const t = useT();
  const url = api.artifactContentUrl(artifactId);
  return (
    <div className={styles.imagePreview}>
      <span className={styles.imagePreviewLabel}>{t("badges.uploadedImagePreview")}</span>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={url}
        alt={t("badges.uploadedImagePreview")}
        className={styles.imagePreviewImg}
      />
      <span className={styles.imagePreviewMeta}>
        {width}×{height} · {mimeType}
      </span>
    </div>
  );
}
