"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type {
  CreateJobFromInputsBody,
  FaceMode,
  UIOptions,
  UploadAudioResponse,
  UploadImageResponse,
  VoiceMode,
} from "@/lib/types";

import { ErrorMessage } from "./ErrorMessage";
import { UploadCard } from "./UploadCard";
import styles from "./CreateJobForm.module.css";

interface CreateJobFormProps {
  readonly uiOptions: UIOptions;
}

export function CreateJobForm({ uiOptions }: CreateJobFormProps) {
  const router = useRouter();
  const [brief, setBrief] = useState("");
  const [duration, setDuration] = useState<number>(
    uiOptions.duration_bounds.default_seconds,
  );
  const [voiceMode, setVoiceMode] = useState<VoiceMode>("tts");
  const [scriptText, setScriptText] = useState("");
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
    };

    try {
      const job = await api.createJobFromInputs(body);
      router.push(`/jobs/${job.id}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      setError(msg);
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
          </div>
        ) : (
          <>
            <UploadCard
              kind="audio"
              title="Provided audio (WAV)"
              help="A pre-recorded narration that you own or that is synthetic."
              acceptExtensions={audioExts}
              maxBytes={audioMax}
              onUploaded={(r) => setAudioArtifact(r as UploadAudioResponse)}
              currentArtifactId={audioArtifact?.artifact_id ?? null}
            />
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
              help="PNG / JPEG / WebP. Must be a synthetic (AI-generated) person."
              acceptExtensions={imageExts}
              maxBytes={imageMax}
              onUploaded={(r) => setImageArtifact(r as UploadImageResponse)}
              currentArtifactId={imageArtifact?.artifact_id ?? null}
            />
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
