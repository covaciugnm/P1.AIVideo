"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

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

import { AudioPreview } from "./AudioPreview";
import { ErrorMessage } from "./ErrorMessage";
import { useSettings } from "./SettingsContext";
import { UploadCard } from "./UploadCard";
import styles from "./CreateJobForm.module.css";

interface CreateJobFormProps {
  readonly uiOptions: UIOptions;
}

export function CreateJobForm({ uiOptions }: CreateJobFormProps) {
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
      setScriptStatus("Fill in the brief first.");
      return;
    }
    scriptAbortRef.current?.abort();
    const controller = new AbortController();
    scriptAbortRef.current = controller;
    setScriptBusy(true);
    setScriptStatus("Generating script…");
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
      `Generated (${res.value.provider_id}/${res.value.model}; ~${res.value.estimated_duration_seconds.toFixed(1)}s).`,
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
    setTtsStatus("Generating…");
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
      const niceMsg =
        res.error.code === "tts_provider_not_configured"
          ? `Provider "${res.error.provider_id}" is not configured. Install the runtime + place voice assets, then enable in Settings.`
          : res.error.message;
      setTtsStatus(niceMsg);
      logBus.emit({
        source: "frontend",
        level: res.httpStatus === 503 ? "warning" : "error",
        message: `tts-generate ${res.error.code}`,
        meta: { code: res.error.code, status: res.httpStatus },
      });
    } else {
      setTtsStatus("Generated.");
      logBus.emit({
        source: "frontend",
        level: "success",
        message: "tts-generate succeeded",
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
      const msg = err instanceof ApiError ? err.detail : String(err);
      setError(msg);
      logBus.emit({
        source: "frontend",
        level: "error",
        message: "create-job failed",
        meta: { error: msg },
      });
      setSubmitting(false);
    }
  };

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <section className="card">
        <h2>1. Brief</h2>
        <div className="field">
          <label htmlFor="brief">Topic / brief</label>
          <textarea
            id="brief"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            maxLength={2000}
            placeholder="e.g. Three calming bedtime habits for better sleep."
            required
          />
          <span className={styles.muted}>{brief.length} / 2000</span>
        </div>
        <div className="field">
          <label htmlFor="duration">Target duration (seconds)</label>
          <input
            id="duration"
            type="number"
            min={durMin}
            max={durMax}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
          />
          <span className={styles.muted}>
            Between {durMin} and {durMax} seconds.
          </span>
        </div>
      </section>

      <section className="card">
        <h2>2. Voice</h2>
        <div className="field">
          <label>Voice source</label>
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
                <span>{vm.label}</span>
              </label>
            ))}
          </div>
        </div>
        {voiceMode === "tts" ? (
          <div className="field">
            <label htmlFor="script">Script text</label>
            <textarea
              id="script"
              value={scriptText}
              onChange={(e) => setScriptText(e.target.value)}
              maxLength={scriptMaxChars}
              placeholder="Open with a hook. End with a single CTA."
              required
            />
            <span className={styles.muted}>
              {scriptText.length} / {scriptMaxChars}
            </span>
            <div className={styles.ttsRow}>
              <button
                type="button"
                className="btn"
                onClick={handleScriptGenerate}
                disabled={scriptBusy || brief.trim().length === 0}
                title={
                  brief.trim().length === 0
                    ? "Fill in the brief first."
                    : "Calls /api/v1/script/generate with the selected LLM provider."
                }
              >
                {scriptBusy ? "Generating script…" : "Generate script"}
              </button>
              <button
                type="button"
                className="btn"
                onClick={handleTtsGenerate}
                disabled={ttsBusy || scriptText.trim().length === 0}
              >
                {ttsBusy ? "Generating audio…" : "Generate audio"}
              </button>
              {scriptStatus && (
                <span className={styles.ttsStatus}>{scriptStatus}</span>
              )}
              {ttsStatus && (
                <span className={styles.ttsStatus}>{ttsStatus}</span>
              )}
            </div>
          </div>
        ) : (
          <>
            <UploadCard
              kind="audio"
              title="Provided audio"
              help={`Accepted: ${audioExts.join(", ")}. Non-WAV is transcoded to PCM WAV on the server (requires ffmpeg). Minimum 1 s; 22050 Hz+ recommended; mono or stereo; synthetic or owned.`}
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
                label="Uploaded audio preview"
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
                <span>
                  I have lawful authority to use this recording (consent
                  confirmed).
                </span>
              </label>
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={audioOwned}
                  onChange={(e) => setAudioOwned(e.target.checked)}
                />
                <span>
                  This recording is either synthetic or a voice I own. Cloning a
                  third party&apos;s voice is not allowed.
                </span>
              </label>
            </div>
          </>
        )}
      </section>

      <section className="card">
        <h2>2b. Providers</h2>
        <p className={styles.muted}>
          Pick a provider per category, or leave blank to use the backend
          default. Unconfigured providers are visible but selecting one
          surfaces a warning later when generation is attempted.
        </p>
        <ProviderField
          label="Script LLM"
          value={llmProvider}
          onChange={setLlmProvider}
          providers={providers?.llm ?? []}
        />
        <ProviderField
          label="TTS"
          value={ttsProvider}
          onChange={setTtsProvider}
          providers={providers?.tts ?? []}
        />
        <ProviderField
          label="Video generator"
          value={videoProvider}
          onChange={setVideoProvider}
          providers={providers?.video_generator ?? []}
        />
        <ProviderField
          label="Audio processor"
          value={audioProcessor}
          onChange={setAudioProcessor}
          providers={providers?.audio_processor ?? []}
        />
        <ProviderField
          label="Image processor"
          value={imageProcessor}
          onChange={setImageProcessor}
          providers={providers?.image_processor ?? []}
        />
      </section>

      <section className="card">
        <h2>3. Face (optional)</h2>
        <label className={styles.checkbox}>
          <input
            type="checkbox"
            checked={useFace}
            onChange={(e) => setUseFace(e.target.checked)}
          />
          <span>Attach a portrait/face image for the face stage.</span>
        </label>
        {useFace && (
          <>
            <UploadCard
              kind="image"
              title="Portrait image"
              help="PNG / JPEG / WebP. ≥ 512×512 recommended (1024×1024+ preferred). Front-facing, well-lit, synthetic (AI-generated) only."
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
                <span>I have lawful authority to use this image.</span>
              </label>
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={imageSynthetic}
                  onChange={(e) => setImageSynthetic(e.target.checked)}
                />
                <span>
                  This image is a synthetic (AI-generated) person. BYO
                  real-person likeness is not allowed.
                </span>
              </label>
            </div>
          </>
        )}
      </section>

      <section className="card">
        <h2>4. Compliance attestations</h2>
        <div className="compliance-banner">
          Every generated reel will carry an AI-content disclosure overlay and
          C2PA-style provenance metadata. No real-person impersonation. No
          voice cloning of others.
        </div>
        <div className={styles.consentBlock}>
          <label className={styles.checkbox}>
            <input
              type="checkbox"
              checked={syntheticPerson}
              onChange={(e) => setSyntheticPerson(e.target.checked)}
            />
            <span>
              I confirm the on-camera person is fully synthetic (not a real
              individual).
            </span>
          </label>
          <label className={styles.checkbox}>
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>
              I confirm I have the rights and consent to produce and publish
              this reel.
            </span>
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
          {submitting ? "Creating job…" : "Create job"}
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
}

function ProviderField({ label, value, onChange, providers }: ProviderFieldProps) {
  const selected = providers.find((p) => p.provider_id === value);
  const warn =
    selected && selected.status !== "available" && selected.status !== "configured";
  return (
    <div className="field">
      <label>{label}</label>
      <select
        className={styles.select}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">— default —</option>
        {providers.map((p) => (
          <option key={p.provider_id} value={p.provider_id}>
            {p.label} ({p.status.replace(/_/g, " ")})
            {p.requires_gpu ? " · GPU" : ""}
            {p.requires_network ? " · network" : ""}
            {p.is_custom ? " · custom" : ""}
          </option>
        ))}
      </select>
      {selected && (
        <span className={styles.providerBadges}>
          {selected.requires_gpu && (
            <span className={styles.badgeGpu} title="GPU required">
              GPU required
            </span>
          )}
          {selected.requires_network && (
            <span className={styles.badgeNet} title="requires network">
              requires network
            </span>
          )}
          {selected.requires_model_files && (
            <span className={styles.badgeAssets} title="requires model files">
              requires model files
            </span>
          )}
          {selected.is_custom && (
            <span className={styles.badgeCustom} title="custom provider — metadata only">
              custom · metadata only
            </span>
          )}
        </span>
      )}
      {warn && (
        <span className={styles.providerWarn}>
          {selected.notes || `${selected.provider_id} is ${selected.status.replace(/_/g, " ")}.`}
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
        Audio fit: <strong>{fitStatus.replace(/_/g, " ")}</strong>
      </span>
      <span className={styles.fitMeta}>
        target {target}s · audio{" "}
        {audioDurationSeconds !== null
          ? `${audioDurationSeconds.toFixed(2)}s`
          : "—"}{" "}
        · Δ {deltaLabel}
      </span>
      {fitStatus !== "ok" && (
        <span className={styles.fitRec}>
          → {recommendation.replace(/_/g, " ")}
        </span>
      )}
    </div>
  );
}

function ImagePreview({ artifactId, width, height, mimeType }: ImagePreviewProps) {
  const url = api.artifactContentUrl(artifactId);
  return (
    <div className={styles.imagePreview}>
      <span className={styles.imagePreviewLabel}>Uploaded image preview</span>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={url}
        alt="Uploaded portrait"
        className={styles.imagePreviewImg}
      />
      <span className={styles.imagePreviewMeta}>
        {width}×{height} · {mimeType}
      </span>
    </div>
  );
}
