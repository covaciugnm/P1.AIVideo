"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ErrorMessage } from "@/components/ErrorMessage";
import { HelpHint } from "@/components/HelpHint";
import { LoadingState } from "@/components/LoadingState";
import { StatusBadge } from "@/components/StatusBadge";
import { useT } from "@/lib/i18n/LanguageContext";
import {
  ApiError,
  getJob,
  getProviders,
  humanizeApiDetail,
  retryJob,
  updateJob,
} from "@/lib/api";
import { isTerminalStatus, shortId } from "@/lib/format";
import * as logBus from "@/lib/log-bus";
import type {
  JobDetail,
  JobStatus,
  JobUpdateBody,
  ProviderInfo,
  ProvidersResponse,
  ProviderSelection,
  VoiceMode,
} from "@/lib/types";

import styles from "./page.module.css";

// Phase 11B — recoverable terminal states. Mirrors the backend policy
// in ``compute_edit_policy``: these are the states where Retry is
// available (and edits to provider_selection are accepted).
const RECOVERABLE: ReadonlySet<JobStatus> = new Set(["rejected", "failed"]);

interface ProviderField {
  readonly key: keyof ProviderSelection;
  readonly category: keyof ProvidersResponse;
  readonly labelKey:
    | "createJob.scriptProvider"
    | "createJob.ttsProvider"
    | "createJob.videoProvider"
    | "createJob.audioProcessor"
    | "createJob.imageProcessor";
}

const PROVIDER_FIELDS: readonly ProviderField[] = [
  {
    key: "script_provider_id",
    category: "llm",
    labelKey: "createJob.scriptProvider",
  },
  {
    key: "tts_provider_id",
    category: "tts",
    labelKey: "createJob.ttsProvider",
  },
  {
    key: "video_provider_id",
    category: "video_generator",
    labelKey: "createJob.videoProvider",
  },
  {
    key: "audio_processor_id",
    category: "audio_processor",
    labelKey: "createJob.audioProcessor",
  },
  {
    key: "image_processor_id",
    category: "image_processor",
    labelKey: "createJob.imageProcessor",
  },
];

const SUBTITLE_FORMATS: readonly ("srt" | "vtt")[] = ["srt", "vtt"];

export default function EditJobPage({
  params,
}: {
  readonly params: { readonly jobId: string };
}) {
  const { jobId } = params;
  const router = useRouter();
  const t = useT();

  const [job, setJob] = useState<JobDetail | null>(null);
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const announcedRef = useRef(false);

  // Form fields.
  const [brief, setBrief] = useState("");
  const [duration, setDuration] = useState(30);
  const [scriptText, setScriptText] = useState("");
  const [voiceMode, setVoiceMode] = useState<VoiceMode>("tts");
  const [providerSelection, setProviderSelection] = useState<ProviderSelection>(
    {},
  );
  const [videoLanguage, setVideoLanguage] = useState("ro");
  const [subtitleEnabled, setSubtitleEnabled] = useState(false);
  const [subtitleLanguagesRaw, setSubtitleLanguagesRaw] = useState("");
  const [subtitleFormat, setSubtitleFormat] = useState<"srt" | "vtt">("srt");
  const [subtitleBurnIn, setSubtitleBurnIn] = useState(false);

  useEffect(() => {
    if (!announcedRef.current) {
      announcedRef.current = true;
      logBus.emit({
        source: "frontend",
        level: "info",
        message: `edit job opened: ${shortId(jobId)}`,
        meta: { jobId },
      });
    }
    const controller = new AbortController();
    (async () => {
      try {
        const [j, p] = await Promise.all([
          getJob(jobId, controller.signal),
          getProviders(controller.signal).catch(() => null),
        ]);
        setJob(j);
        setBrief(j.brief);
        setDuration(j.target_duration_seconds);
        setScriptText(j.script_text ?? "");
        setVoiceMode(((j.voice_mode as VoiceMode) || "tts") as VoiceMode);
        setProviderSelection({ ...(j.provider_selection ?? {}) });
        setVideoLanguage(j.video_language ?? "ro");
        setSubtitleEnabled(Boolean(j.subtitle_enabled));
        setSubtitleLanguagesRaw(
          (j.subtitle_languages ?? []).join(", "),
        );
        setSubtitleFormat(((j.subtitle_format ?? "srt") as "srt" | "vtt"));
        setSubtitleBurnIn(Boolean(j.subtitle_burn_in));
        if (p) setProviders(p);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        const msg = err instanceof ApiError ? err.detail : String(err);
        setLoadError(msg);
      }
    })();
    return () => controller.abort();
  }, [jobId]);

  if (loadError) {
    return (
      <div>
        <Link href="/jobs" className="muted">
          {t("jobDetail.backToJobs")}
        </Link>
        <ErrorMessage message={loadError} title={t("editJob.failedToLoad")} />
      </div>
    );
  }
  if (!job) {
    return <LoadingState label={t("editJob.loadingJob")} />;
  }

  const status = job.status as JobStatus;
  const terminalPublished = status === "published";
  const canEdit = job.can_edit ?? !terminalPublished;
  const canRetry = (job.can_retry ?? RECOVERABLE.has(status)) && !terminalPublished;
  const lockedFields = new Set(job.locked_fields ?? []);
  const showProviderSection =
    status === "pending_compliance" || RECOVERABLE.has(status);

  const initialSubtitleLangs = (job.subtitle_languages ?? []).join(", ");
  const subtitleLangsChanged =
    subtitleLanguagesRaw.trim() !== initialSubtitleLangs.trim();

  const briefChanged = brief !== job.brief;
  const durationChanged = duration !== job.target_duration_seconds;
  const scriptChanged = (scriptText || null) !== (job.script_text || null);
  const voiceModeChanged = voiceMode !== (job.voice_mode as VoiceMode);
  const providerSelectionChanged = (() => {
    const current = (job.provider_selection ?? {}) as Record<string, unknown>;
    const next = providerSelection as Record<string, unknown>;
    const keys = new Set([...Object.keys(current), ...Object.keys(next)]);
    for (const k of keys) {
      const a = current[k] ?? null;
      const b = next[k] ?? null;
      if (a !== b) return true;
    }
    return false;
  })();
  const videoLanguageChanged = videoLanguage !== (job.video_language ?? "ro");
  const subtitleEnabledChanged =
    subtitleEnabled !== Boolean(job.subtitle_enabled);
  const subtitleFormatChanged =
    subtitleFormat !== (job.subtitle_format ?? "srt");
  const subtitleBurnInChanged =
    subtitleBurnIn !== Boolean(job.subtitle_burn_in);

  const hasChanges =
    briefChanged ||
    durationChanged ||
    scriptChanged ||
    voiceModeChanged ||
    providerSelectionChanged ||
    videoLanguageChanged ||
    subtitleEnabledChanged ||
    subtitleLangsChanged ||
    subtitleFormatChanged ||
    subtitleBurnInChanged;
  const canSubmit = hasChanges && !submitting && canEdit;

  const updateProvider = (
    field: keyof ProviderSelection,
    value: string,
  ): void => {
    setProviderSelection((prev) => {
      const next = { ...prev };
      if (value === "") {
        delete next[field];
      } else {
        (next as Record<string, string>)[field as string] = value;
      }
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);
    setSavedAt(null);

    // JobUpdateBody fields are declared readonly to discourage mutation
    // after the request is built; the builder assembles the payload via
    // a locally-mutable mirror and casts back when it's ready to send.
    type MutablePatch = { -readonly [K in keyof JobUpdateBody]?: JobUpdateBody[K] };
    const patch: MutablePatch = {};
    if (briefChanged) patch.brief = brief.trim();
    if (durationChanged) patch.target_duration_seconds = duration;
    if (scriptChanged) patch.script_text = scriptText.trim();
    if (voiceModeChanged) patch.voice_mode = voiceMode;
    if (providerSelectionChanged) {
      // Send only the non-empty fields; backend treats unset as
      // "leave as-is" because we filter None server-side.
      const clean: Record<string, string> = {};
      for (const [k, v] of Object.entries(providerSelection)) {
        if (typeof v === "string" && v.length > 0) {
          clean[k] = v;
        }
      }
      patch.provider_selection = clean as ProviderSelection;
    }
    if (videoLanguageChanged) patch.video_language = videoLanguage;
    if (subtitleEnabledChanged) patch.subtitle_enabled = subtitleEnabled;
    if (subtitleLangsChanged) {
      const langs = subtitleLanguagesRaw
        .split(",")
        .map((s) => s.trim())
        .filter((s) => s.length > 0);
      patch.subtitle_languages = langs;
    }
    if (subtitleFormatChanged) patch.subtitle_format = subtitleFormat;
    if (subtitleBurnInChanged) patch.subtitle_burn_in = subtitleBurnIn;

    logBus.emit({
      source: "frontend",
      level: "info",
      message: `edit-job submitted: ${shortId(jobId)}`,
      meta: { jobId, fields: Object.keys(patch) },
    });

    try {
      const updated = await updateJob(jobId, patch as JobUpdateBody);
      logBus.emit({
        source: "frontend",
        level: "success",
        message: `edit-job succeeded: ${shortId(jobId)}`,
        meta: { jobId, status: updated.status },
      });
      setJob(updated as JobDetail);
      setSavedAt(new Date().toISOString());
      setSubmitting(false);
      // If the job is not in a recoverable state, return to the
      // detail page so the operator can continue the normal flow.
      if (!RECOVERABLE.has(updated.status as JobStatus)) {
        router.push(`/jobs/${jobId}`);
      }
    } catch (err) {
      const msg =
        err instanceof ApiError ? humanizeApiDetail(err.detail) : String(err);
      setSubmitError(msg);
      setSubmitting(false);
      logBus.emit({
        source: "frontend",
        level: "error",
        message: `edit-job failed: ${shortId(jobId)}`,
        meta: { jobId, error: msg },
      });
    }
  };

  const handleRetry = async () => {
    if (!canRetry) return;
    if (hasChanges) {
      setSubmitError(t("editJob.saveBeforeRetry"));
      return;
    }
    setRetrying(true);
    setSubmitError(null);
    try {
      await retryJob(jobId, { reason: "operator-edit-then-retry" });
      logBus.emit({
        source: "frontend",
        level: "success",
        message: `retry-after-edit: ${shortId(jobId)}`,
        meta: { jobId },
      });
      router.push(`/jobs/${jobId}`);
    } catch (err) {
      const msg =
        err instanceof ApiError ? humanizeApiDetail(err.detail) : String(err);
      setSubmitError(msg);
      setRetrying(false);
    }
  };

  return (
    <div>
      <header className={styles.header}>
        <Link href={`/jobs/${jobId}`} className="muted">
          {t("editJob.backToJob")}
        </Link>
        <h1 className={styles.title}>
          {t("jobDetail.editJob")} <code>{shortId(jobId)}</code>{" "}
          <StatusBadge status={status} />
          <HelpHint slug="edit-job" />
        </h1>
      </header>

      {terminalPublished && (
        <div className="card">
          <p className="muted">
            {t("editJob.publishedLockedNote")}
          </p>
        </div>
      )}

      {!canEdit && !terminalPublished && (
        <div className="card">
          <p className="muted">{t("editJob.cannotEditCurrent")}</p>
        </div>
      )}

      {canEdit && lockedFields.size > 0 && (
        <div className="compliance-banner">
          {t("editJob.someFieldsLocked")}
        </div>
      )}

      {RECOVERABLE.has(status) && (
        <div className="compliance-banner">
          {t("editJob.providerChangeableBeforeRetry")}
        </div>
      )}

      {savedAt && (
        <div className="card">
          <p>{t("editJob.changesSaved")}</p>
        </div>
      )}

      <form className={styles.form} onSubmit={handleSubmit}>
        <section className="card">
          <h2>{t("editJob.editable")}</h2>
          <div className="field">
            <label htmlFor="brief">{t("editJob.briefLabel")}</label>
            <textarea
              id="brief"
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              maxLength={2000}
              disabled={!canEdit}
              required
            />
            <span className={styles.muted}>{brief.length} / 2000</span>
          </div>
          <div className="field">
            <label htmlFor="duration">{t("editJob.targetDurationLabel")}</label>
            <input
              id="duration"
              type="number"
              min={15}
              max={60}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              disabled={!canEdit}
            />
          </div>
          <div className="field">
            <label htmlFor="voice_mode">{t("jobDetail.voiceMode")}</label>
            <select
              id="voice_mode"
              value={voiceMode}
              onChange={(e) =>
                setVoiceMode(e.target.value as VoiceMode)
              }
              disabled={!canEdit || lockedFields.has("voice_mode")}
            >
              <option value="tts">{t("createJob.voiceTts")}</option>
              <option value="provided_audio">
                {t("createJob.voiceProvided")}
              </option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="script">{t("editJob.scriptTextLabel")}</label>
            <textarea
              id="script"
              value={scriptText}
              onChange={(e) => setScriptText(e.target.value)}
              maxLength={8000}
              disabled={!canEdit || lockedFields.has("script_text")}
            />
            <span className={styles.muted}>
              {scriptText.length} / 8000
            </span>
          </div>
        </section>

        {showProviderSection && (
          <section className="card">
            <h2>
              {t("createJob.sectionProviders")}{" "}
              <HelpHint slug="provider-selection" small />
            </h2>
            <p className="muted">{t("editJob.providerEditIntro")}</p>
            <dl className="kv">
              {PROVIDER_FIELDS.map((pf) => {
                const list = (providers?.[pf.category] ?? []) as readonly ProviderInfo[];
                const fieldLocked = !canEdit || lockedFields.has("provider_selection");
                const current = (providerSelection[pf.key] as string | undefined) ?? "";
                return (
                  <ProviderRow
                    key={pf.key}
                    label={t(pf.labelKey)}
                    value={current}
                    providers={list}
                    disabled={fieldLocked}
                    inheritLabel={t("createJob.providerInherit")}
                    onChange={(v) => updateProvider(pf.key, v)}
                  />
                );
              })}
            </dl>
          </section>
        )}

        <section className="card">
          <h2>{t("createJob.sectionLanguage")}</h2>
          <div className="field">
            <label htmlFor="video_language">{t("createJob.videoLanguage")}</label>
            <input
              id="video_language"
              type="text"
              value={videoLanguage}
              onChange={(e) => setVideoLanguage(e.target.value.trim())}
              maxLength={8}
              disabled={!canEdit || lockedFields.has("video_language")}
            />
          </div>
          <div className="field">
            <label>
              <input
                type="checkbox"
                checked={subtitleEnabled}
                onChange={(e) => setSubtitleEnabled(e.target.checked)}
                disabled={!canEdit || lockedFields.has("subtitle_enabled")}
              />{" "}
              {t("createJob.enableSubtitles")}
            </label>
          </div>
          {subtitleEnabled && (
            <>
              <div className="field">
                <label htmlFor="subtitle_languages">
                  {t("createJob.subtitleLanguages")}
                </label>
                <input
                  id="subtitle_languages"
                  type="text"
                  value={subtitleLanguagesRaw}
                  onChange={(e) => setSubtitleLanguagesRaw(e.target.value)}
                  placeholder="ro, en"
                  disabled={
                    !canEdit || lockedFields.has("subtitle_languages")
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="subtitle_format">
                  {t("createJob.subtitleFormat")}
                </label>
                <select
                  id="subtitle_format"
                  value={subtitleFormat}
                  onChange={(e) =>
                    setSubtitleFormat(e.target.value as "srt" | "vtt")
                  }
                  disabled={!canEdit || lockedFields.has("subtitle_format")}
                >
                  {SUBTITLE_FORMATS.map((f) => (
                    <option key={f} value={f}>
                      {f.toUpperCase()}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>
                  <input
                    type="checkbox"
                    checked={subtitleBurnIn}
                    onChange={(e) => setSubtitleBurnIn(e.target.checked)}
                    disabled={!canEdit || lockedFields.has("subtitle_burn_in")}
                  />{" "}
                  {t("createJob.burnSubtitles")}
                </label>
              </div>
            </>
          )}
        </section>

        <section className="card">
          <h2>{t("editJob.readOnly")}</h2>
          <dl className="kv">
            {job.face_mode && (
              <>
                <dt>{t("jobDetail.faceMode")}</dt>
                <dd>{job.face_mode}</dd>
              </>
            )}
            <dt>{t("jobDetail.ttsBackend")}</dt>
            <dd>{job.tts_backend}</dd>
            <dt>{t("jobDetail.watermarkRequired")}</dt>
            <dd>
              {job.watermark_required ? t("common.yes") : t("common.no")}
            </dd>
            <dt>{t("jobDetail.c2paRequired")}</dt>
            <dd>{job.c2pa_required ? t("common.yes") : t("common.no")}</dd>
            {job.rejection_reason && (
              <>
                <dt>{t("jobDetail.rejectionReason")}</dt>
                <dd>{job.rejection_reason}</dd>
              </>
            )}
          </dl>
        </section>

        {submitError && (
          <ErrorMessage
            message={submitError}
            title={t("editJob.updateRejected")}
          />
        )}

        <div className={styles.actions}>
          <Link href={`/jobs/${jobId}`} className="btn btn-ghost">
            {t("common.cancel")}
          </Link>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!canSubmit}
          >
            {submitting ? t("editJob.saving") : t("editJob.saveChanges")}
          </button>
          {canRetry && (
            <button
              type="button"
              className="btn btn-primary"
              disabled={hasChanges || retrying}
              onClick={handleRetry}
              title={
                hasChanges ? t("editJob.saveBeforeRetry") : undefined
              }
            >
              {retrying ? t("jobDetail.retrying") : t("editJob.retryAfterEdit")}
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

function ProviderRow({
  label,
  value,
  providers,
  disabled,
  inheritLabel,
  onChange,
}: {
  readonly label: string;
  readonly value: string;
  readonly providers: readonly ProviderInfo[];
  readonly disabled: boolean;
  readonly inheritLabel: string;
  readonly onChange: (next: string) => void;
}) {
  return (
    <>
      <dt>{label}</dt>
      <dd>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        >
          <option value="">{inheritLabel}</option>
          {providers.map((p) => (
            <option key={p.provider_id} value={p.provider_id}>
              {p.label || p.provider_id} ({p.status})
            </option>
          ))}
          {/* If the current value isn't in the live catalog (e.g.
              custom_future_tts), still surface it so the operator can
              see and replace it. */}
          {value &&
            !providers.some((p) => p.provider_id === value) && (
              <option value={value}>{value} (custom)</option>
            )}
        </select>
      </dd>
    </>
  );
}
