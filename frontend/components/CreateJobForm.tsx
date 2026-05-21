"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import * as logBus from "@/lib/log-bus";
import type {
  CreateJobFromInputsBody,
  FaceMode,
  ProviderInfo,
  ProvidersResponse,
  SceneSpec,
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
import { AuthImage } from "./AuthImage";
import { ProgressBar } from "./ProgressBar";
import { ProviderStatusBadge } from "./ProviderStatusBadge";
import { useSettings } from "./SettingsContext";
import { UploadCard } from "./UploadCard";
import styles from "./CreateJobForm.module.css";
import {
  type CharacterSummary,
  listCharacters,
} from "@/lib/characters";

// Phase 20 — display labels for the language-picker dropdown. Unknown
// ISO codes fall back to the upper-cased code itself, so adding a new
// TTS language (e.g. ``hu`` for Hungarian) only needs an entry here.
const LANG_LABEL: Record<string, string> = {
  ro: "Română",
  en: "English",
  es: "Español",
  fr: "Français",
  de: "Deutsch",
  it: "Italiano",
  pt: "Português",
  pl: "Polski",
  hu: "Magyar",
};

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
  const [ttsElapsed, setTtsElapsed] = useState(0); // seconds, for the progress bar
  const [ttsChunks, setTtsChunks] = useState<{ done: number; total: number } | null>(null);
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
  // Phase 18 iter 2 — two-step generation:
  //   1. brief → LLM scenariu → "scenario" (high-level outline, readonly)
  //   2. scenario (or brief) → LLM text scenariu → "script_text" (editable)
  // The two LLM picks are kept separate so the operator can use a
  // different model per step (e.g. fast template for the outline, real
  // LLM for the dialogue).
  const [scenarioText, setScenarioText] = useState<string>("");
  const [scenarioBusy, setScenarioBusy] = useState(false);
  const [scenarioStatus, setScenarioStatus] = useState<string | null>(null);
  const scenarioAbortRef = useRef<AbortController | null>(null);
  const [textScriptLlmProvider, setTextScriptLlmProvider] = useState<string | null>(null);
  // Phase 21 iter 2 — FLUX character image generation state.
  // generatedImageArtifactId is what's sent as image_artifact_id at
  // submit time; generatedImageUrl renders the inline preview.
  const [generatedImageArtifactId, setGeneratedImageArtifactId] = useState<string | null>(null);
  const [generatedImageUrl, setGeneratedImageUrl] = useState<string | null>(null);
  const [imageGenBusy, setImageGenBusy] = useState(false);
  const [imageGenStatus, setImageGenStatus] = useState<string | null>(null);
  const imageGenAbortRef = useRef<AbortController | null>(null);
  // Phase 21 — scene_plan editable state for scenes_only / news_presenter.
  const [scenePlan, setScenePlan] = useState<SceneSpec[]>([]);
  const [scenePlanBusy, setScenePlanBusy] = useState(false);
  const [scenePlanStatus, setScenePlanStatus] = useState<string | null>(null);
  const scenePlanAbortRef = useRef<AbortController | null>(null);
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
  // Phase 21 — job type chooser (Step 0). THREE distinct job types
  // each with their own form layout + backend DAG:
  //   - talking_head  : single portrait + lipsync (the original flow)
  //   - scenes_only   : no character; voiceover over B-roll scene
  //                     images generated by FLUX/SD3.5
  //   - news_presenter: hybrid — talking-head segments interleaved
  //                     with B-roll scene clips
  // talking_head is wired today; scenes_only + news_presenter route
  // to the same scene-plan UI but with different DAGs (no presenter
  // segments for scenes_only).
  const [jobType, setJobType] = useState<
    "talking_head" | "scenes_only" | "news_presenter"
  >("talking_head");
  // Phase 22 — output orientation (mobile vertical / landscape / square).
  const [orientation, setOrientation] = useState<
    "landscape" | "portrait" | "square"
  >("landscape");
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

  // Phase 18 — when a character is selected, fetch its full profile so
  // the form can read profile.identity.gender for TTS gender filtering.
  // Phase 20 — also pulls native_language + spoken_languages so the
  // video-language dropdown can be seeded from the character's actual
  // language coverage.
  const [selectedCharGender, setSelectedCharGender] = useState<string | null>(null);
  const [selectedCharLanguages, setSelectedCharLanguages] = useState<readonly string[]>([]);
  // Character's fixed TTS voice (when arriving from a character). null = not locked.
  const [lockedVoice, setLockedVoice] = useState<string | null>(null);
  useEffect(() => {
    if (!characterId) {
      setSelectedCharGender(null);
      setSelectedCharLanguages([]);
      return;
    }
    const ctrl = new AbortController();
    void (async () => {
      try {
        const { getCharacter } = await import("@/lib/characters");
        const full = await getCharacter(characterId, ctrl.signal);
        const identity = full?.profile?.identity as
          | { gender?: string | null; native_language?: string | null; spoken_languages?: readonly string[] }
          | undefined;
        if (typeof identity?.gender === "string") setSelectedCharGender(identity.gender.toLowerCase());
        else setSelectedCharGender(null);
        // TTS is unique per character — lock it to the character's voice when
        // the operator arrived from that character.
        if (fromCharacter && full?.default_voice_provider_id) {
          setLockedVoice(full.default_voice_provider_id);
          setTtsProvider(full.default_voice_provider_id);
        }
        // Build the language set: native_language plus spoken_languages,
        // de-duplicated, lower-cased. Empty list when the operator hasn't
        // filled either field — falls back to all TTS-supported languages.
        const langs = new Set<string>();
        if (identity?.native_language) langs.add(identity.native_language.toLowerCase());
        for (const l of identity?.spoken_languages ?? []) {
          if (typeof l === "string" && l) langs.add(l.toLowerCase());
        }
        setSelectedCharLanguages([...langs]);
      } catch { /* ignore */ }
    })();
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [characterId]);

  // Phase 17 — prefill from URL query params:
  //   ?character_id=...&brief=... → pre-populate the form when the user
  //   clicks "Generate video with this image" from the character image
  //   library. Runs once at mount, only when fields are empty so we
  //   don't clobber operator edits.
  const searchParams = useSearchParams();
  // Arriving from a character's image gallery (?character_id&image_id) puts the
  // form in a locked, simplified mode: character fixed + source photo shown;
  // only Text-audio + Video sections visible; everything else uses defaults.
  const fromCharacter = Boolean(searchParams?.get("character_id"));
  const sourceImageId = searchParams?.get("image_id") || null;
  // Use the source character photo directly as the job's portrait.
  useEffect(() => {
    const cid = searchParams?.get("character_id");
    const iid = searchParams?.get("image_id");
    if (!cid || !iid) return;
    const ctrl = new AbortController();
    void (async () => {
      try {
        const { listCharacterImages } = await import("@/lib/characters");
        const r = await listCharacterImages(cid, ctrl.signal);
        const img = r.items.find((i) => i.id === iid);
        if (img?.artifact_id) {
          setGeneratedImageArtifactId(img.artifact_id);
          setGeneratedImageUrl(`${api.getActiveApiBaseUrl()}/api/v1/characters/${cid}/images/${iid}/content`);
        }
      } catch { /* ignore */ }
    })();
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
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
        // Default LLM = Qwen3.6 27b when available; else first usable.
        // Applies to both the scenariu + text-script pickers.
        if (!settings.defaultLlmProvider) {
          const usable = (p.llm ?? []).filter(isUsableProvider);
          const qwen = usable.find((x) =>
            /qwen\s*3\.?6/i.test(`${x.provider_id} ${x.label ?? ""}`),
          );
          const pick = qwen ?? usable[0];
          if (pick) {
            setLlmProvider((prev) => prev ?? pick.provider_id);
            setTextScriptLlmProvider((prev) => prev ?? pick.provider_id);
          }
        }
        // Default video engine = best-quality RUNNABLE talking-head/lip-sync
        // engine. Quality order (best first); fall back to first usable.
        const VIDEO_QUALITY = ["hallo", "echomimic", "musetalk", "liveportrait", "sadtalker", "wav2lip"];
        const vids = (p.video_generator ?? []).filter(isUsableProvider);
        const bestVideo =
          VIDEO_QUALITY.map((id) => vids.find((v) => v.provider_id === id)).find(Boolean)
          ?? vids[0];
        if (bestVideo) {
          setVideoProvider((prev) => (fromCharacter ? bestVideo.provider_id : (prev ?? bestVideo.provider_id)));
        }
      } catch {
        // Providers panel is optional; the form still works.
      }
    })();
    return () => controller.abort();
    // Run once on mount; reading settings.defaultLlmProvider here is a
    // one-shot prefill, not a reactive dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Phase 18 — scenariu = high-level outline from brief.
  const handleScenarioGenerate = async () => {
    if (brief.trim().length < 50) {
      setScenarioStatus(t("createJob.briefMinChars"));
      return;
    }
    scenarioAbortRef.current?.abort();
    const controller = new AbortController();
    scenarioAbortRef.current = controller;
    setScenarioBusy(true);
    setScenarioStatus(t("createJob.generateScriptBusy"));
    const res = await api.generateScript(
      {
        brief: brief.trim(),
        target_duration_seconds: duration,
        script_text: null,
        // Phase 20 iter 2 — without language the backend defaults to
        // "en" and the cinematic prompt produces English JSON even
        // for Romanian briefs. Always thread videoLanguage through.
        language: videoLanguage,
        provider_id: llmProvider ?? "template",
        // Phase 21 iter 2 — the talking-head form's "Generate scenariu"
        // button now produces an IMAGE DESCRIPTION (background +
        // outfit) used to render the still portrait via FLUX. The
        // character's gender goes through ``tone`` (the cheap channel
        // already in ScriptRequest) so the prompt builder can frame
        // the right body.
        mode: "image_description",
        tone: selectedCharGender ?? undefined,
      },
      controller.signal,
    );
    setScenarioBusy(false);
    if (!res.ok) {
      setScenarioStatus(`${res.error.code.replace(/_/g, " ")}: ${res.error.message}`);
      return;
    }
    setScenarioText(res.value.full_script);
    setScenarioStatus(
      t("createJob.scriptGeneratedStatus", {
        provider: res.value.provider_id,
        model: res.value.model,
        duration: res.value.estimated_duration_seconds.toFixed(1),
      }),
    );
  };

  // Phase 21 — generate the scene plan via the LLM. Used by both
  // scenes_only and news_presenter job types. Pre-fills the editable
  // scene list which the operator can then tweak before submitting.
  const handleGenerateScenePlan = async () => {
    if (brief.trim().length < 50) {
      setScenePlanStatus(t("createJob.briefMinChars"));
      return;
    }
    if (jobType === "talking_head") {
      // Defensive — UI hides the button for talking_head, but guard
      // anyway in case shortcut keys trigger it.
      return;
    }
    scenePlanAbortRef.current?.abort();
    const controller = new AbortController();
    scenePlanAbortRef.current = controller;
    setScenePlanBusy(true);
    setScenePlanStatus(t("createJob.scenePlanBusy"));
    const res = await api.generateScript(
      {
        brief: brief.trim(),
        target_duration_seconds: duration,
        script_text: null,
        language: videoLanguage,
        provider_id: llmProvider ?? "template",
        mode: "scene_plan",
        job_type_hint: jobType,
        character_gender: selectedCharGender ?? undefined,
      },
      controller.signal,
    );
    setScenePlanBusy(false);
    if (!res.ok) {
      setScenePlanStatus(
        `${res.error.code.replace(/_/g, " ")}: ${res.error.message}`,
      );
      return;
    }
    const scenes = res.value.scenes ?? [];
    if (!scenes.length) {
      setScenePlanStatus(t("createJob.scenePlanEmpty"));
      return;
    }
    setScenePlan(scenes.map((s) => ({ ...s })));
    setScenePlanStatus(
      t("createJob.scenePlanDone", {
        count: String(scenes.length),
        provider: res.value.provider_id,
      }),
    );
  };

  // Phase 21 — scene_plan editing helpers.
  const updateScene = (idx: number, patch: Partial<SceneSpec>) => {
    setScenePlan((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  };
  const deleteScene = (idx: number) => {
    setScenePlan((prev) =>
      prev
        .filter((_, i) => i !== idx)
        .map((s, i) => ({ ...s, scene_number: i + 1 })),
    );
  };
  const moveScene = (idx: number, dir: -1 | 1) => {
    setScenePlan((prev) => {
      const next = [...prev];
      const newIdx = idx + dir;
      if (newIdx < 0 || newIdx >= next.length) return prev;
      [next[idx], next[newIdx]] = [next[newIdx], next[idx]];
      return next.map((s, i) => ({ ...s, scene_number: i + 1 }));
    });
  };
  const addScene = (kind: "presenter" | "broll") => {
    setScenePlan((prev) => [
      ...prev,
      {
        scene_number: prev.length + 1,
        kind,
        spoken_text: "",
        visual_description: kind === "broll" ? "" : null,
        duration_s: 5,
        image_artifact_id: null,
        audio_artifact_id: null,
        clip_artifact_id: null,
      },
    ]);
  };

  // Phase 21 iter 2 — call character_image_service via FLUX with the
  // (LLM-proposed and operator-edited) image description as prompt.
  // Returns an image_artifact_id we use at submit time so the lipsync
  // stage runs against the freshly-generated portrait.
  const handleGenerateImage = async () => {
    if (!characterId) {
      setImageGenStatus(t("createJob.imageGenNoCharacter"));
      return;
    }
    const prompt = scenarioText.trim();
    if (prompt.length < 10) {
      setImageGenStatus(t("createJob.imageGenNeedDesc"));
      return;
    }
    imageGenAbortRef.current?.abort();
    const controller = new AbortController();
    imageGenAbortRef.current = controller;
    setImageGenBusy(true);
    setImageGenStatus(t("createJob.imageGenBusy"));
    try {
      const { generateCharacterImage } = await import("@/lib/characters");
      const res = await generateCharacterImage(
        characterId,
        {
          prompt,
          provider_id: "flux_local",
          width: 1024,
          height: 1024,
          steps: 4,
          guidance_scale: 0,
          use_main_reference: true,
          notes: "auto-generated from CreateJobForm image description",
        },
        controller.signal,
      );
      setImageGenBusy(false);
      if (!res.ok) {
        setImageGenStatus(
          `${res.error.error_code.replace(/_/g, " ")}: ${res.error.detail}`,
        );
        setGeneratedImageArtifactId(null);
        setGeneratedImageUrl(null);
        return;
      }
      const img = res.value;
      const baseUrl = api.getActiveApiBaseUrl();
      // Prefer the global artifact (visible to job submit); fall back
      // to the character-image content URL for preview.
      const url = img.artifact_id
        ? `${baseUrl}/api/v1/artifacts/${img.artifact_id}/content`
        : (img.local_url ? `${baseUrl}${img.local_url}` : null);
      setGeneratedImageArtifactId(img.artifact_id ?? null);
      setGeneratedImageUrl(url);
      setImageGenStatus(
        t("createJob.imageGenDone", {
          provider: img.provider_id ?? "flux_local",
          width: String(img.width ?? "?"),
          height: String(img.height ?? "?"),
        }),
      );
    } catch (err) {
      setImageGenBusy(false);
      setImageGenStatus((err as Error).message);
    }
  };

  const handleScriptGenerate = async () => {
    // Phase 21 iter 3 — bug fix: scenarioText now holds the English
    // FLUX image prompt (Phase 21 iter 2 repurposed the textarea),
    // so using it as the seed for the SPOKEN script would produce a
    // voiceover about the image composition instead of the brief's
    // actual subject. Always use the original brief as the seed.
    if (!brief.trim()) {
      setScriptStatus(t("badges.fillBriefFirst"));
      return;
    }
    scriptAbortRef.current?.abort();
    const controller = new AbortController();
    scriptAbortRef.current = controller;
    setScriptBusy(true);
    setScriptStatus(t("createJob.generateScriptBusy"));
    const seedBrief = brief.trim();
    logBus.emit({
      source: "frontend",
      level: "info",
      message: `script-generate (text scenariu) start (provider=${textScriptLlmProvider ?? llmProvider ?? "template"})`,
    });
    const res = await api.generateScript(
      {
        brief: seedBrief,
        target_duration_seconds: duration,
        script_text: scriptText.trim() || null,
        // Phase 20 iter 2 — thread the picked language; default-"en"
        // backed off the prior bug.
        language: videoLanguage,
        provider_id: textScriptLlmProvider ?? llmProvider ?? "template",
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
    // Live elapsed timer so the operator sees progress — F5 TTS can take
    // ~40-60s (CPU / GPU-contended), which otherwise looks frozen.
    const t0 = Date.now();
    setTtsElapsed(0);
    setTtsStatus("Se generează audio… (poate dura ~40-60s)");
    const timer = window.setInterval(() => {
      setTtsElapsed(Math.round((Date.now() - t0) / 1000));
    }, 1000);
    // Hard cap so it never spins forever — F5 on CPU is ~27s per ~180-char
    // chunk, so long paragraphs blow past any reasonable wait. Abort + advise.
    const CAP_MS = 180_000;
    let timedOut = false;
    const killTimer = window.setTimeout(() => { timedOut = true; controller.abort(); }, CAP_MS);
    logBus.emit({
      source: "frontend",
      level: "info",
      message: `tts-generate start (provider=${ttsProvider ?? "default"})`,
      meta: { provider_id: ttsProvider ?? "default" },
    });
    window.clearTimeout(killTimer); // async job survives long runs; no hard cap
    void timedOut;
    const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));
    try {
      // Submit a background job, then poll for progress (chunk N/M) until done.
      const job = await api.generateTtsAsync({
        script_text: scriptText.trim(),
        tts_provider_id: ttsProvider ?? "piper",
      });
      setTtsChunks({ done: job.chunks_done, total: job.chunks_total });
      let final = job;
      const POLL_DEADLINE = Date.now() + 1_200_000; // 20 min safety cap
      while (final.status === "queued" || final.status === "running") {
        if (controller.signal.aborted || Date.now() > POLL_DEADLINE) break;
        await sleep(2000);
        try {
          final = await api.getTtsJob(job.id);
          setTtsChunks({ done: final.chunks_done, total: final.chunks_total });
        } catch { /* transient — keep polling */ }
      }
      window.clearInterval(timer);
      setTtsBusy(false);
      if (final.status === "done" && final.artifact_id) {
        setTtsArtifact({
          artifact_id: final.artifact_id,
          provider_id: final.provider_id,
          voice_id: final.voice_id ?? "",
          mime_type: "audio/wav",
          size_bytes: 0,
          duration_seconds: 0,
          sample_rate: 0,
          channels: 0,
        });
        setTtsStatus(null);
        logBus.emit({ source: "frontend", level: "success", message: "tts-async done", meta: { artifact_id: final.artifact_id } });
      } else if (final.status === "error") {
        setTtsArtifact(null);
        setTtsStatus(null);
        setError(final.error_message || "Generarea audio a eșuat.");
      } else {
        setTtsStatus(null);
        setError("Generarea audio a depășit timpul de așteptare. Verifică starea jobului mai târziu.");
      }
    } catch (err) {
      window.clearInterval(timer);
      setTtsBusy(false);
      setError((err as Error).message);
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

  // Phase 20 — compute the language dropdown options from the catalog.
  // Source of truth: the set of languages declared by usable TTS
  // providers whose voice_gender matches the selected character (or
  // is neutral/unspecified). Intersect with the character's
  // spoken_languages if the operator filled that profile field;
  // otherwise fall back to every TTS language so the dropdown is
  // never empty for characters with incomplete profiles.
  const availableLanguages = useMemo(() => {
    const ttsRows = providers?.tts ?? [];
    const charGender = (selectedCharGender || "").toLowerCase();
    const langs = new Set<string>();
    for (const p of ttsRows) {
      if (!isUsableProvider(p)) continue;
      const pg = (p.voice_gender || "").toLowerCase();
      if (charGender && pg && pg !== "neutral" && pg !== charGender) continue;
      const l = (p.language || "").toLowerCase();
      if (l) langs.add(l);
    }
    const arr = [...langs];
    if (selectedCharLanguages.length === 0) return arr.sort();
    const charSet = new Set(selectedCharLanguages);
    const inter = arr.filter((l) => charSet.has(l));
    return (inter.length > 0 ? inter : arr).sort();
  }, [providers, selectedCharGender, selectedCharLanguages]);

  // Reset videoLanguage when it falls out of the available set (e.g.
  // operator switched from a Romanian character to an English-only one).
  useEffect(() => {
    if (availableLanguages.length === 0) return;
    if (!availableLanguages.includes(videoLanguage)) {
      setVideoLanguage(availableLanguages[0]);
    }
  }, [availableLanguages, videoLanguage]);
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(false);
  // Phase 21 — independent subtitle TEXT language. Empty string =
  // "same as videoLanguage" (i.e. captions in the spoken language).
  const [subtitleTextLanguage, setSubtitleTextLanguage] = useState<string>("");
  const [subtitleLangsRo, setSubtitleLangsRo] = useState(true);
  const [subtitleLangsEn, setSubtitleLangsEn] = useState(false);
  const [subtitleFormat, setSubtitleFormat] = useState<"srt" | "vtt">("srt");
  const [subtitleBurnIn, setSubtitleBurnIn] = useState(false);

  const [syntheticPerson, setSyntheticPerson] = useState(false);
  const [consent, setConsent] = useState(false);
  // From-character flow hides the compliance section — the persona is already
  // vetted, so auto-assert synthetic + consent.
  useEffect(() => {
    if (fromCharacter) { setSyntheticPerson(true); setConsent(true); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromCharacter]);

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
    // Phase 18 — minimum 50 chars for brief + script_text (gating for
    // Generate Script / Generate Audio / Submit Job). Brief is hidden in the
    // from-character flow, so it isn't gated there.
    (fromCharacter || brief.trim().length >= 50) &&
    // Phase 17 — character REQUIRED for talking_head + news_presenter
    // (scenes_only has no character on screen).
    (jobType === "scenes_only" || characterId.length > 0) &&
    duration >= durMin &&
    duration <= durMax &&
    // Compliance section is hidden in the from-character flow; the character
    // is already a vetted synthetic persona, so consent is auto-asserted.
    (fromCharacter || (syntheticPerson && consent)) &&
    // Phase 21 — voice / scene_plan gates per job_type.
    // - talking_head: script_text OR audio artifact (as before)
    // - scenes_only / news_presenter: scene_plan with ≥1 scene, all
    //   spoken_text non-empty; broll scenes also need visual_description
    (jobType === "talking_head"
      ? (voiceMode === "tts"
        ? scriptText.trim().length >= 50
        : audioArtifact !== null && audioConsent && audioOwned)
      : (scenePlan.length > 0
        && scenePlan.every((s) => (s.spoken_text || "").trim().length > 0)
        && scenePlan
          .filter((s) => s.kind === "broll")
          .every((s) => (s.visual_description || "").trim().length > 0))) &&
    // Phase 21 iter 2 — a FLUX-generated image counts as an
    // acceptable face source (the operator was the one that triggered
    // generation, so the synthetic + consent flags are implied).
    // For scenes_only, no face is needed.
    (jobType === "scenes_only"
      || generatedImageArtifactId !== null
      || !useFace
      || (imageArtifact !== null && imageConsent && imageSynthetic)) &&
    !submitting;

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);

    // Phase 21 iter 2 — when a FLUX image was generated, treat the job
    // as provided_image automatically (the operator vetted it inline
    // by clicking "Generate image" and accepting the preview).
    const faceMode: FaceMode | null =
      generatedImageArtifactId ? "provided_image" : (useFace ? "provided_image" : null);

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
      // Phase 21 iter 2 — prefer the freshly FLUX-generated image
      // over any manually-uploaded one. When operator clicked
      // "Generate image", that's their authoritative pick.
      image_artifact_id:
        generatedImageArtifactId
        ?? (useFace ? imageArtifact?.artifact_id ?? null : null),
      image_consent_confirmed:
        generatedImageArtifactId !== null
          ? true
          : (useFace ? imageConsent : false),
      image_synthetic_person_confirmed:
        generatedImageArtifactId !== null
          ? true
          : (useFace ? imageSynthetic : false),
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
      // Phase 21 — explicit subtitle TEXT language override. When the
      // operator left the picker empty (= "use spoken language"), don't
      // send the field so the backend treats it as null and the
      // captions default to the spoken language.
      transcript_language: subtitleTextLanguage || null,
      // Phase 12 — optional persona binding.
      character_id: characterId || null,
      // Phase 21 — pipeline variant + per-scene plan.
      job_type: jobType,
      scene_plan: jobType !== "talking_head" ? scenePlan : null,
      // Phase 22 — output orientation.
      orientation,
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
      {/* Phase 21 — Step 0: job-type chooser. THREE distinct types,
          each with its own form layout below and its own backend DAG.
          Current scope (this commit): the chooser + scoping label
          changes. talking_head submits today; scenes_only +
          news_presenter route to the new scene-plan form (next
          sub-phase). */}
      {!fromCharacter && (
      <section className="card" data-testid="jobtype-section">
        <h2 style={{ marginBottom: 6 }}>{t("createJob.sectionJobType")}</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
          {t("createJob.jobTypeIntro")}
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginTop: 8 }}>
          {(
            [
              { id: "talking_head", labelKey: "jobTypeTalkingHead", descKey: "jobTypeTalkingHeadDesc", live: true },
              { id: "scenes_only", labelKey: "jobTypeScenesOnly", descKey: "jobTypeScenesOnlyDesc", live: true },
              { id: "news_presenter", labelKey: "jobTypeNewsPresenter", descKey: "jobTypeNewsPresenterDesc", live: true },
            ] as const
          ).map((opt) => (
            <label
              key={opt.id}
              className="card"
              style={{
                padding: 10,
                borderColor: jobType === opt.id ? "var(--accent, #6db5ff)" : undefined,
                borderWidth: 2,
                borderStyle: "solid",
                cursor: "pointer",
                display: "flex",
                alignItems: "flex-start",
                gap: 8,
                opacity: opt.live ? 1 : 0.85,
              }}
            >
              <input
                type="radio"
                name="job-type"
                value={opt.id}
                checked={jobType === opt.id}
                onChange={() => setJobType(opt.id)}
                style={{ marginTop: 4 }}
              />
              <div>
                <strong>
                  {t(`createJob.${opt.labelKey}` as never)}{" "}
                  {!opt.live && (
                    <small style={{ color: "var(--warn, #f5b955)", fontWeight: 400 }}>
                      ({t("createJob.jobTypeComingSoon")})
                    </small>
                  )}
                </strong>
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  {t(`createJob.${opt.descKey}` as never)}
                </div>
              </div>
            </label>
          ))}
        </div>
        {/* Phase 21 — both scenes_only and news_presenter are now live;
            the pending banner has been removed. */}
        {/* Phase 22 — output format / orientation selector. */}
        <div style={{ marginTop: 12 }}>
          <label style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>
            {t("createJob.orientationLabel")}
          </label>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {(
              [
                { id: "landscape", icon: "▭", ratio: "16:9", key: "orientationLandscape" },
                { id: "portrait",  icon: "▯", ratio: "9:16", key: "orientationPortrait" },
                { id: "square",    icon: "◻", ratio: "1:1",  key: "orientationSquare" },
              ] as const
            ).map((o) => (
              <label
                key={o.id}
                style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "8px 14px", borderRadius: 6, cursor: "pointer",
                  border: "2px solid " + (orientation === o.id ? "var(--accent, #6db5ff)" : "var(--border)"),
                  background: orientation === o.id ? "rgba(109,181,255,0.08)" : "transparent",
                }}
              >
                <input
                  type="radio" name="orientation" value={o.id}
                  checked={orientation === o.id}
                  onChange={() => setOrientation(o.id)}
                  style={{ display: "none" }}
                />
                <span style={{ fontSize: 20 }}>{o.icon}</span>
                <span>
                  <strong>{t(`createJob.${o.key}` as never)}</strong>
                  <span className="muted" style={{ marginLeft: 6, fontSize: 12 }}>{o.ratio}</span>
                </span>
              </label>
            ))}
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            {t("createJob.orientationHelp")}
          </p>
        </div>
      </section>
      )}
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
        {fromCharacter ? (
          /* Locked: came from a character. Show name (read-only) + the source
             photo we started from (if any). The character cannot be changed. */
          <div className="field" style={{ display: "flex", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
            {sourceImageId && characterId && (
              <AuthImage
                src={`${api.getActiveApiBaseUrl()}/api/v1/characters/${characterId}/images/${sourceImageId}/content`}
                alt="poza sursă"
                style={{ width: 110, height: "auto", borderRadius: 8, border: "1px solid var(--border)" }}
              />
            )}
            <div>
              <strong>{selectedCharacter?.display_name || selectedCharacter?.name || characterId}</strong>
              <div className="muted" style={{ fontSize: 12 }}>
                🔒 Personaj fix · {selectedCharacter?.default_language ?? "—"}
              </div>
            </div>
          </div>
        ) : (
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
        )}
        {!fromCharacter && selectedCharacter && (
          <div className="card" style={{ marginTop: 8, padding: 8 }}>
            <strong>{t("characters.summary.title")}: {selectedCharacter.display_name || selectedCharacter.name}</strong>
            <div className="muted" style={{ fontSize: 12 }}>
              {t("characters.summary.language")}: {selectedCharacter.default_language ?? t("characters.summary.none")}
              {" · "}
              {t("characters.summary.gender")}: {(() => {
                const g = (selectedCharGender || "").toLowerCase();
                if (g === "female" || g === "femeie" || g === "f") return t("characters.summary.genderFemale");
                if (g === "male" || g === "barbat" || g === "bărbat" || g === "m") return t("characters.summary.genderMale");
                if (g) return g;
                return t("characters.summary.none");
              })()}
            </div>
          </div>
        )}
        {/* Phase 20 iter 2 — language picker MOVED inside the character
            card so the operator sees character + spoken language as a
            single decision. Inline (label · select) to avoid a full
            field row. */}
        <div className="field" style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, marginBottom: 0 }}>
          <label htmlFor="video-language-picker" title={t("createJob.videoLanguageHelp")} style={{ margin: 0, whiteSpace: "nowrap" }}>
            {t("createJob.videoLanguage")}:
          </label>
          <select
            id="video-language-picker"
            value={videoLanguage}
            onChange={(e) => setVideoLanguage(e.target.value)}
            title={t("createJob.videoLanguageHelp")}
            style={{ width: "auto" }}
          >
            {availableLanguages.length === 0 && (
              <option value="" disabled>
                {t("createJob.languageNoneAvailable")}
              </option>
            )}
            {availableLanguages.map((lang) => (
              <option key={lang} value={lang}>
                {LANG_LABEL[lang] ?? lang.toUpperCase()}
              </option>
            ))}
          </select>
          {selectedCharLanguages.length > 0 && (
            <small className="muted" style={{ fontWeight: 400 }}>
              ({t("createJob.characterLanguagesNote")}: {selectedCharLanguages.join(", ")})
            </small>
          )}
        </div>
      </section>
      {!fromCharacter && (
      <section className="card">
        <h2>1. {t("createJob.sectionBrief").replace(/^\d+\.\s*/, "")} <HelpHint slug="create-job" small /></h2>
        <div className="field">
          <label htmlFor="brief" title={t("createJob.briefHelp")}>
            {t("createJob.briefLabel")}
          </label>
          <textarea
            id="brief"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            maxLength={2000}
            placeholder={t("createJob.briefPlaceholder")}
            title={t("createJob.briefHelp")}
            required
          />
          <span className={styles.muted}>
            {brief.length} / 2000
            {brief.trim().length < 50 && (
              <span style={{ marginLeft: 8, color: "var(--warn, #f5b955)" }}>
                ⚠ {t("createJob.briefMinChars")}
              </span>
            )}
          </span>
        </div>
        {/* Phase 18 iter 2 + Phase 20 iter 2 — LLM scenariu picker +
            Generate button packed on a SINGLE compact row. No flex-grow
            on the select wrapper so the button hugs the dropdown. */}
        <div className="field" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 4 }}>
          <label title={t("createJob.scriptProviderHelp")} style={{ margin: 0, whiteSpace: "nowrap" }}>
            {t("createJob.scriptProvider")}:
          </label>
          <select
            className={styles.select}
            value={llmProvider ?? ""}
            onChange={(e) => setLlmProvider(e.target.value || null)}
            title={t("createJob.scriptProviderHelp")}
            style={{ width: "auto", maxWidth: 320 }}
          >
            <option value="">{t("createJob.providerInherit")}</option>
            {(providers?.llm ?? [])
              .filter((p) => isUsableProvider(p) || p.provider_id === llmProvider || p.provider_id === textScriptLlmProvider)
              .map((p) => (
                <option key={p.provider_id} value={p.provider_id}>
                  {p.label} ({t(`providerStatuses.${p.status}` as never)})
                </option>
              ))}
          </select>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleScenarioGenerate}
            disabled={scenarioBusy || brief.trim().length < 50}
            title={
              brief.trim().length < 50
                ? t("createJob.briefMinChars")
                : t("createJob.generateScriptHelp")
            }
          >
            {scenarioBusy ? t("createJob.generateScriptBusy") : t("createJob.generateScenario")}
          </button>
          {scenarioStatus && (
            <small className="muted" style={{ fontSize: 12 }}>{scenarioStatus}</small>
          )}
        </div>
        {/* Phase 21 iter 2 — image description textarea (was readonly
            scenario preview). The LLM now produces an English FLUX
            prompt describing the still portrait's background + outfit;
            the operator can tweak it before clicking "Generate image". */}
        <div className="field" style={{ marginBottom: 4 }}>
          <label title={t("createJob.imageDescHelp")} style={{ marginBottom: 2 }}>
            {t("createJob.imageDescLabel")}{" "}
            <small className="muted" style={{ fontWeight: 400 }}>
              ({t("createJob.imageDescEditableNote")})
            </small>
          </label>
          <textarea
            value={scenarioText}
            onChange={(e) => setScenarioText(e.target.value)}
            rows={3}
            placeholder={t("createJob.imageDescEmpty")}
            style={{
              width: "100%", boxSizing: "border-box",
              padding: "8px", fontFamily: "inherit",
              border: "1px solid var(--border)", borderRadius: 6,
              background: "rgba(255,255,255,0.04)", color: "var(--text)",
              minHeight: 64,
            }}
            title={t("createJob.imageDescHelp")}
          />
          {/* Phase 21 iter 2 — Generate image button + preview. Calls
              the existing character_image_service through the character
              endpoint so the new portrait is registered as an artifact
              the lipsync stage can pick up via face_mode=provided_image. */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 6 }}>
            <button
              type="button"
              className="btn"
              onClick={handleGenerateImage}
              disabled={imageGenBusy || !characterId || scenarioText.trim().length < 10}
              title={
                !characterId
                  ? t("createJob.imageGenNoCharacter")
                  : scenarioText.trim().length < 10
                    ? t("createJob.imageGenNeedDesc")
                    : t("createJob.imageGenHelp")
              }
            >
              {imageGenBusy
                ? t("createJob.imageGenBusy")
                : t("createJob.imageGenButton")}
            </button>
            {imageGenStatus && (
              <small className="muted" style={{ fontSize: 12 }}>{imageGenStatus}</small>
            )}
          </div>
          {generatedImageUrl && (
            <div style={{ marginTop: 6 }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={generatedImageUrl}
                alt={t("createJob.imageGenPreviewAlt")}
                style={{
                  maxWidth: "100%", maxHeight: 280,
                  borderRadius: 6, border: "1px solid var(--border)",
                  display: "block",
                }}
              />
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4, flexWrap: "wrap" }}>
                <small className="muted" style={{ fontSize: 11, flex: 1 }}>
                  ✓ {t("createJob.imageGenPreviewNote")}
                </small>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => {
                    setGeneratedImageArtifactId(null);
                    setGeneratedImageUrl(null);
                    setImageGenStatus(null);
                  }}
                  title={t("createJob.imageGenClearHelp")}
                  style={{ fontSize: 12, padding: "4px 10px" }}
                >
                  {t("createJob.imageGenClear")}
                </button>
              </div>
            </div>
          )}
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
      )}

      {/* Phase 21 — Scene plan editor card. Shown only for scenes_only
          and news_presenter. The operator clicks "Generate plan", the
          LLM proposes a list, then each card is editable inline. */}
      {jobType !== "talking_head" && (
        <section className="card">
          <h2>
            {t("createJob.sectionScenePlan")}{" "}
            <small className="muted" style={{ fontWeight: 400, fontSize: "0.7em" }}>
              ({jobType === "scenes_only"
                ? t("createJob.jobTypeScenesOnly")
                : t("createJob.jobTypeNewsPresenter")})
            </small>
          </h2>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleGenerateScenePlan}
              disabled={scenePlanBusy || brief.trim().length < 50}
              title={
                brief.trim().length < 50
                  ? t("createJob.briefMinChars")
                  : t("createJob.scenePlanHelp")
              }
            >
              {scenePlanBusy
                ? t("createJob.scenePlanBusy")
                : (scenePlan.length > 0
                  ? t("createJob.scenePlanRegenerate")
                  : t("createJob.scenePlanGenerate"))}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => addScene("broll")}
              title={t("createJob.scenePlanAddBrollHelp")}
              style={{ fontSize: 12 }}
            >
              + {t("createJob.scenePlanAddBroll")}
            </button>
            {jobType === "news_presenter" && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => addScene("presenter")}
                title={t("createJob.scenePlanAddPresenterHelp")}
                style={{ fontSize: 12 }}
              >
                + {t("createJob.scenePlanAddPresenter")}
              </button>
            )}
            {scenePlan.length > 0 && (
              <small className="muted" style={{ fontSize: 12 }}>
                {t("createJob.scenePlanTotal", {
                  count: String(scenePlan.length),
                  total: scenePlan
                    .reduce((acc, s) => acc + (s.duration_s || 0), 0)
                    .toFixed(1),
                })}
              </small>
            )}
            {scenePlanStatus && (
              <small className="muted" style={{ fontSize: 12 }}>{scenePlanStatus}</small>
            )}
          </div>
          {scenePlan.length === 0 && (
            <p className="muted" style={{ fontSize: 12 }}>
              {t("createJob.scenePlanEmptyPlaceholder")}
            </p>
          )}
          {scenePlan.map((s, idx) => (
            <div
              key={idx}
              className="card"
              style={{
                marginTop: 8, padding: 10,
                borderColor: s.kind === "presenter" ? "var(--accent, #6db5ff)" : "var(--border)",
                borderWidth: 2, borderStyle: "solid",
              }}
            >
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
                <strong style={{ minWidth: 60 }}>#{s.scene_number}</strong>
                <select
                  value={s.kind}
                  onChange={(e) => updateScene(idx, {
                    kind: e.target.value as "presenter" | "broll",
                    visual_description: e.target.value === "presenter" ? null : (s.visual_description ?? ""),
                  })}
                  disabled={jobType === "scenes_only"}
                  style={{ width: "auto" }}
                  title={t("createJob.scenePlanKindHelp")}
                >
                  <option value="presenter">{t("createJob.scenePlanKindPresenter")}</option>
                  <option value="broll">{t("createJob.scenePlanKindBroll")}</option>
                </select>
                <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
                  {t("createJob.scenePlanDuration")}:
                  <input
                    type="number"
                    min={1}
                    max={20}
                    step={0.5}
                    value={s.duration_s}
                    onChange={(e) => updateScene(idx, { duration_s: Number(e.target.value) })}
                    style={{ width: 70 }}
                  />s
                </label>
                <span style={{ flex: 1 }} />
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => moveScene(idx, -1)}
                  disabled={idx === 0}
                  title={t("createJob.scenePlanMoveUp")}
                  style={{ fontSize: 11, padding: "2px 6px" }}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => moveScene(idx, 1)}
                  disabled={idx === scenePlan.length - 1}
                  title={t("createJob.scenePlanMoveDown")}
                  style={{ fontSize: 11, padding: "2px 6px" }}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => deleteScene(idx)}
                  title={t("createJob.scenePlanDelete")}
                  style={{ fontSize: 11, padding: "2px 6px", color: "var(--danger, #f06a6a)" }}
                >
                  ✕
                </button>
              </div>
              <label style={{ fontSize: 12, display: "block", marginBottom: 2 }}>
                {t("createJob.scenePlanSpokenText")}:
              </label>
              <textarea
                value={s.spoken_text}
                onChange={(e) => updateScene(idx, { spoken_text: e.target.value })}
                rows={2}
                placeholder={t("createJob.scenePlanSpokenPlaceholder")}
                style={{
                  width: "100%", boxSizing: "border-box", padding: 6,
                  fontFamily: "inherit", border: "1px solid var(--border)",
                  borderRadius: 4, background: "rgba(255,255,255,0.04)",
                  color: "var(--text)", marginBottom: 4,
                }}
              />
              {s.kind === "broll" && (
                <>
                  <label style={{ fontSize: 12, display: "block", marginBottom: 2 }}>
                    {t("createJob.scenePlanVisualDesc")} (EN):
                  </label>
                  <textarea
                    value={s.visual_description ?? ""}
                    onChange={(e) => updateScene(idx, { visual_description: e.target.value })}
                    rows={2}
                    placeholder={t("createJob.scenePlanVisualPlaceholder")}
                    style={{
                      width: "100%", boxSizing: "border-box", padding: 6,
                      fontFamily: "inherit", border: "1px solid var(--border)",
                      borderRadius: 4, background: "rgba(255,255,255,0.04)",
                      color: "var(--text)",
                    }}
                  />
                </>
              )}
              {s.kind === "presenter" && (
                <small className="muted" style={{ fontSize: 11 }}>
                  {t("createJob.scenePlanPresenterNote")}
                </small>
              )}
            </div>
          ))}
        </section>
      )}

      {/* The voice + TTS section is hidden for non-talking-head jobs;
          scene_composer handles per-scene TTS automatically. */}
      {jobType === "talking_head" && (
      <>
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
            <label htmlFor="script" title={t("createJob.scriptTextHelp")}>
              {t("createJob.scriptText")}
            </label>
            <textarea
              id="script"
              value={scriptText}
              onChange={(e) => setScriptText(e.target.value)}
              maxLength={scriptMaxChars}
              placeholder={t("createJob.scriptPlaceholder")}
              title={t("createJob.scriptTextHelp")}
              required
            />
            <span className={styles.muted}>
              {t("createJob.scriptCounter", { n: scriptText.length, max: scriptMaxChars })}
              {scriptText.trim().length < 50 && (
                <span style={{ marginLeft: 8, color: "var(--warn, #f5b955)" }}>
                  ⚠ {t("createJob.scriptMinChars")}
                </span>
              )}
            </span>
            {/* Stacked: model picker on its own line, button full-width below. */}
            <div className="field voice-row">
              <label title={t("createJob.textScriptProviderHelp")} style={{ margin: 0 }}>
                {t("createJob.textScriptProvider")}:
              </label>
              <select
                className={styles.select}
                value={textScriptLlmProvider ?? ""}
                onChange={(e) => setTextScriptLlmProvider(e.target.value || null)}
                title={t("createJob.textScriptProviderHelp")}
                style={{ width: "100%" }}
              >
                <option value="">{t("createJob.providerInherit")}</option>
                {(providers?.llm ?? [])
                  .filter((p) => isUsableProvider(p) || p.provider_id === llmProvider || p.provider_id === textScriptLlmProvider)
                  .map((p) => (
                    <option key={p.provider_id} value={p.provider_id}>
                      {p.label} ({t(`providerStatuses.${p.status}` as never)})
                    </option>
                  ))}
              </select>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  // Phase 20 iter 3 — when the script field is already
                  // populated, ask before overwriting. The previous build
                  // disabled the button silently which left the operator
                  // wondering why clicking "Generate text scenariu" did
                  // nothing.
                  if (scriptText.trim().length > 0) {
                    if (!window.confirm(t("createJob.generateTextScriptOverwriteConfirm"))) {
                      return;
                    }
                  }
                  void handleScriptGenerate();
                }}
                disabled={
                  scriptBusy
                  || brief.trim().length < 50
                }
                title={
                  scriptBusy
                    ? t("createJob.generateScriptBusy")
                    : brief.trim().length < 50
                      ? t("createJob.generateTextScriptDisabledNoSource")
                      : scriptText.trim().length > 0
                        ? t("createJob.generateTextScriptOverwriteHint")
                        : t("createJob.generateTextScriptHelp")
                }
              >
                {scriptBusy ? t("createJob.generateScriptBusy") : t("createJob.generateTextScript")}
              </button>
              {scriptStatus && (
                <small className="muted" style={{ fontSize: 12 }}>{scriptStatus}</small>
              )}
            </div>

            {/* Stacked: TTS (fixed for the character) → Generare Audio button. */}
            <div className="field voice-row">
              <label title={t("createJob.ttsProviderHelp")} style={{ margin: 0 }}>
                {t("createJob.ttsProvider")}:
              </label>
              {lockedVoice ? (
                <span title="Vocea TTS este unică pentru acest personaj" style={{ fontWeight: 600 }}>
                  🔒 {(providers?.tts ?? []).find((p) => p.provider_id === lockedVoice)?.label ?? lockedVoice}
                </span>
              ) : (
              <select
                className={styles.select}
                value={ttsProvider ?? ""}
                onChange={(e) => setTtsProvider(e.target.value || null)}
                title={t("createJob.ttsProviderHelp")}
                style={{ width: "auto", maxWidth: 360 }}
              >
                  <option value="">{t("createJob.providerInherit")}</option>
                  {(providers?.tts ?? []).filter((p) => {
                    // Always keep the currently-selected row.
                    if (p.provider_id === ttsProvider) return true;
                    if (!isUsableProvider(p)) return false;
                    // Language filter (Phase 20). Voices without a
                    // declared language are kept as "compatible with all"
                    // so legacy providers don't disappear.
                    const pl = (p.language || "").toLowerCase();
                    if (pl && videoLanguage && pl !== videoLanguage.toLowerCase()) {
                      return false;
                    }
                    // Gender filter (Phase 18). Neutral / unknown voices
                    // are still shown for any character.
                    if (selectedCharGender) {
                      const pg = (p.voice_gender || "").toLowerCase();
                      if (pg && pg !== "neutral" && pg !== selectedCharGender) {
                        return false;
                      }
                    }
                    return true;
                  }).map((p) => {
                    const gender = (p.voice_gender || "").toLowerCase();
                    const lang = (p.language || "").toLowerCase();
                    const annot: string[] = [];
                    if (lang) annot.push(lang);
                    if (gender) annot.push(gender);
                    return (
                      <option key={p.provider_id} value={p.provider_id}>
                        {p.label}
                        {annot.length > 0 ? ` [${annot.join("·")}]` : ""}
                        {" "}({t(`providerStatuses.${p.status}` as never)})
                      </option>
                    );
                  })}
              </select>
              )}
              <button
                type="button"
                className="btn"
                onClick={handleTtsGenerate}
                disabled={ttsBusy || scriptText.trim().length < 50}
                title={
                  scriptText.trim().length < 50
                    ? t("createJob.scriptMinChars")
                    : t("createJob.generateAudioHelp")
                }
              >
                {ttsBusy ? t("createJob.generateAudioBusy") : t("createJob.generateAudio")}
              </button>
              {ttsStatus && (
                <small className="muted" style={{ fontSize: 12 }}>{ttsStatus}</small>
              )}
            </div>
            {/* Audio generation status: 🔴 not generated / 🟡 generating /
                🟢 done, followed by the audio title. */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, fontSize: 13 }}>
              <span style={{ fontSize: 14 }}>
                {ttsBusy ? "🟡" : ttsArtifact ? "🟢" : "🔴"}
              </span>
              <span className="muted">
                {ttsBusy
                  ? `Se generează audio… ${ttsChunks && ttsChunks.total > 0 ? `bucata ${ttsChunks.done}/${ttsChunks.total} · ` : ""}${ttsElapsed}s`
                  : ttsArtifact
                  ? `Audio gata — ${(brief || "audio").replace(/[^a-zA-Z0-9_.-]+/g, "_")}`
                  : "Audio negenerat"}
              </span>
            </div>
            {(ttsBusy || ttsArtifact) && (
              <ProgressBar
                percent={
                  !ttsBusy
                    ? 100
                    : ttsChunks && ttsChunks.total > 0
                    ? Math.min(99, Math.round((ttsChunks.done / ttsChunks.total) * 100))
                    : Math.min(95, Math.round((ttsElapsed / 50) * 100))
                }
              />
            )}
            {/* Phase 20 — per-voice sample preview. Full-width row,
                shown only when a voice with sample_audio_url is picked. */}
            {(() => {
              // Hide the per-voice sample bar when the voice is locked (from
              // a character) — it was an empty/duplicate player; the real
              // audio bar appears after generation below.
              if (lockedVoice) return null;
              const sel = (providers?.tts ?? []).find((p) => p.provider_id === ttsProvider);
              if (!sel?.sample_audio_url) return null;
              const baseUrl = api.getActiveApiBaseUrl();
              const sampleUrl = `${baseUrl}${sel.sample_audio_url}`;
              return (
                <div style={{ marginTop: 4, marginBottom: 4 }}>
                  {sel.sample_text && (
                    <small className="muted" style={{ fontSize: 12, display: "block", marginBottom: 2 }}>
                      <em>“{sel.sample_text}”</em>
                    </small>
                  )}
                  <audio
                    controls
                    preload="none"
                    src={sampleUrl}
                    style={{ width: "100%", height: 30 }}
                  >
                    {t("createJob.samplePlayUnsupported")}
                  </audio>
                </div>
              );
            })()}
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

      {/* 'Furnizori' section removed — providers are inferred from the character/defaults and shown inline next to LLM/TTS. */}
      </>
      )}

      {/* Face section: needed for talking_head + news_presenter (both
          use a character portrait). scenes_only is B-roll only — no
          portrait, so the upload card is hidden. Hidden too when arriving
          from a character (the source photo is already the portrait). */}
      {!fromCharacter && jobType !== "scenes_only" && (
      <section className="card">
        <h2>{t("createJob.sectionFace")} <HelpHint slug="image-upload" small /></h2>
        {/* Phase 21 iter 3 — when a FLUX image was generated above,
            the manual upload UI becomes redundant. Show a clear banner
            with thumbnail + "use this" / "switch to manual upload"
            options so the operator always knows which portrait the
            lipsync stage will receive. */}
        {generatedImageArtifactId && generatedImageUrl ? (
          <div
            style={{
              padding: 10,
              borderRadius: 6,
              background: "rgba(109,216,150,0.08)",
              border: "1px solid var(--ok, #6dd896)",
              display: "flex",
              gap: 12,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={generatedImageUrl}
              alt={t("createJob.imageGenPreviewAlt")}
              style={{
                width: 80, height: 80, objectFit: "cover",
                borderRadius: 4, border: "1px solid var(--border)",
              }}
            />
            <div style={{ flex: "1 1 200px", minWidth: 200 }}>
              <strong style={{ color: "var(--ok, #6dd896)" }}>
                ✓ {t("createJob.faceUsingGeneratedTitle")}
              </strong>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                {t("createJob.faceUsingGeneratedDesc")}
              </div>
            </div>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setGeneratedImageArtifactId(null);
                setGeneratedImageUrl(null);
                setImageGenStatus(null);
              }}
              title={t("createJob.imageGenClearHelp")}
              style={{ fontSize: 12 }}
            >
              {t("createJob.faceSwitchToManual")}
            </button>
          </div>
        ) : null}
        <label className={styles.checkbox} style={{ marginTop: 8 }}>
          <input
            type="checkbox"
            checked={useFace}
            onChange={(e) => setUseFace(e.target.checked)}
            disabled={generatedImageArtifactId !== null}
          />
          <span>{t("createJob.useProvidedImage")}</span>
        </label>
        {useFace && !generatedImageArtifactId && (
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
      )}

      {!fromCharacter && (
      <section className="card">
        <h2>{t("createJob.sectionLanguage")} <HelpHint slug="subtitles" small /></h2>
        <p className="muted" style={{ marginTop: -8, marginBottom: 12 }}>
          {t("createJob.languageSectionSubtitleIntro")}
        </p>
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
                <small className="muted">({t("createJob.burnSubtitlesNote")})</small>
              </span>
            </label>
            {/* Phase 21 — independent subtitle TEXT language. The
                operator can have RO spoken voice + EN captions, for
                example. Empty = inherit from spoken language. */}
            <div className="field" style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
              <label htmlFor="subtitle-text-lang" title={t("createJob.subtitleTextLanguageHelp")} style={{ margin: 0, whiteSpace: "nowrap" }}>
                {t("createJob.subtitleTextLanguage")}:
              </label>
              <select
                id="subtitle-text-lang"
                value={subtitleTextLanguage}
                onChange={(e) => setSubtitleTextLanguage(e.target.value)}
                title={t("createJob.subtitleTextLanguageHelp")}
                style={{ width: "auto" }}
              >
                <option value="">
                  {t("createJob.subtitleTextLanguageSameAsSpoken")} ({videoLanguage})
                </option>
                {availableLanguages
                  .filter((l) => l !== videoLanguage)
                  .map((l) => (
                    <option key={l} value={l}>
                      {LANG_LABEL[l] ?? l.toUpperCase()}
                    </option>
                  ))}
                {/* Also offer the two static fallbacks if no TTS
                    provider declared them — operator can still pick
                    them for sidecar text generation. */}
                {!availableLanguages.includes("en") && videoLanguage !== "en" && (
                  <option value="en">English</option>
                )}
                {!availableLanguages.includes("ro") && videoLanguage !== "ro" && (
                  <option value="ro">Română</option>
                )}
              </select>
            </div>
          </>
        )}
      </section>
      )}

      {!fromCharacter && (
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
      )}

      {/* Video section (from-character flow): engine + lip-sync selectors,
          default = first runnable ranked by quality; generate button to the right. */}
      {fromCharacter && (
      <section className="card">
        <h2>Video</h2>
        <div className="voice-row">
          <label style={{ margin: 0 }}>Motor video</label>
          <select
            value={videoProvider ?? ""}
            onChange={(e) => setVideoProvider(e.target.value || null)}
            style={{ width: "100%" }}
          >
            <option value="">{t("createJob.providerInherit")}</option>
            {(providers?.video_generator ?? [])
              .filter((p) => isUsableProvider(p) || p.provider_id === videoProvider)
              .map((p) => (
                <option key={p.provider_id} value={p.provider_id}>
                  {p.label} ({t(`providerStatuses.${p.status}` as never)})
                </option>
              ))}
          </select>
          <small className="muted" style={{ fontSize: 11 }}>
            Lip-sync este realizat de motorul video selectat (ex. SadTalker / Wav2Lip).
          </small>
        </div>
      </section>
      )}

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
  readonly help?: string;
  // Phase 20 — when true (default), only providers with status
  // "available" or "configured" are listed. Toggle off in admin /
  // diagnostic UIs that want to show the full catalog including
  // not_implemented / not_configured rows.
  readonly usableOnly?: boolean;
}

// Phase 20 — central definition of which provider statuses are
// considered "usable" in a job-creation dropdown. Anything else is
// filtered out so the operator can't pick a provider the backend will
// reject at runtime.
export function isUsableProvider(p: ProviderInfo): boolean {
  return p.status === "available" || p.status === "configured";
}

function ProviderField({
  label,
  value,
  onChange,
  providers,
  defaultFromSettings,
  help,
  usableOnly = true,
}: ProviderFieldProps) {
  const t = useT();
  // Phase 20 — filter to usable providers. The current selection is
  // always retained (even if it became unusable since the page was
  // loaded) so the operator can see + fix it.
  const visibleProviders = usableOnly
    ? providers.filter((p) => isUsableProvider(p) || p.provider_id === value)
    : providers;
  const selected = providers.find((p) => p.provider_id === value);
  const warn =
    selected && selected.status !== "available" && selected.status !== "configured";
  const defaultLabel = defaultFromSettings
    ? t("createJob.providerInheritWithName").replace("{name}", defaultFromSettings)
    : t("createJob.providerInherit");
  return (
    <div className="field">
      <label title={help}>{label}</label>
      <select
        className={styles.select}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">{defaultLabel}</option>
        {visibleProviders.map((p) => (
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
