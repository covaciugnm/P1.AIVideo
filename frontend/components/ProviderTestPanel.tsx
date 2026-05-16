"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  artifactContentUrl,
  generateScript,
  generateTts,
  getActiveApiBaseUrl,
  getProviders,
  humanizeApiDetail,
} from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageContext";
import * as logBus from "@/lib/log-bus";
import type { ProviderCategory, ProviderInfo, ProvidersResponse } from "@/lib/types";

import styles from "./ProviderTestPanel.module.css";

// ---------------------------------------------------------------------------
// Per-category configuration. ``status`` colour bucket + human-friendly
// per-error-code copy. Kept in this file (close to the UI that uses it)
// so the operator-facing strings live next to the test code.
// ---------------------------------------------------------------------------

type StatusBucket = "ok" | "warn" | "error" | "muted";

const _STATUS_BUCKET: Record<string, StatusBucket> = {
  available: "ok",
  configured: "ok",
  ready: "ok",
  not_configured: "warn",
  disabled: "warn",
  runtime_missing: "error",
  assets_missing: "error",
  gpu_missing: "error",
  gpu_unavailable: "error",
  error: "error",
  not_implemented: "muted",
};


const _ERROR_GUIDE: Record<string, string> = {
  script_provider_disabled:
    "Network calls are disabled. Enable SCRIPTWRITER_ENABLE_NETWORK_CALLS=true and configure the provider before retrying.",
  script_provider_not_configured:
    "Provider exists in the catalog but its env / endpoint is not set. See docs/runbooks/ollama-scriptwriter.md.",
  script_provider_not_implemented:
    "Provider is a registry stub. The generate() body is not wired yet.",
  script_provider_unreachable:
    "The provider's daemon did not respond. Check OLLAMA_BASE_URL, network routing, and that the daemon process is up.",
  script_model_missing:
    "The Ollama daemon is reachable, but the requested model is not pulled. Run `ollama pull <model>` on the daemon host or pick another model — no auto-pull from this app.",
  script_generation_failed:
    "Generation reached the daemon but the response was malformed or the call failed. Check the backend logs.",
  tts_runtime_missing:
    "Piper runtime is not installed in this image. Run `pip install piper-tts` and rebuild the backend.",
  tts_assets_missing:
    "Piper voice files are not on disk under PIPER_MODELS_ROOT. Place .onnx + .onnx.json manually — no auto-download.",
  tts_provider_not_configured:
    "TTS provider config is missing. Set PIPER_MODELS_ROOT (or TTS_MODELS_ROOT).",
  tts_provider_not_implemented:
    "TTS provider is a catalog stub — no real synthesis path wired yet.",
  video_runtime_missing:
    "torch is not importable in this image. Real SadTalker inference runs from the GPU image (Dockerfile.cuda).",
  video_gpu_missing:
    "No CUDA device visible. Check NVIDIA driver + Container Toolkit (`make docker-gpu-smoke`).",
  video_assets_missing:
    "SadTalker weights are not on disk under SADTALKER_MODELS_ROOT. Place the five files manually — no auto-download.",
  video_provider_not_configured:
    "SADTALKER_MODELS_ROOT is unset. Set it in .env and restart the backend.",
  video_provider_not_implemented:
    "Default state: real-inference flags off. Flip SADTALKER_ENABLE_REAL_INFERENCE=true + RUN_REAL_SADTALKER=1 once weights + GPU are in place (Phase 7D).",
  video_generation_failed:
    "The real inference path ran and reported a non-zero exit. See backend logs for the truncated ffmpeg/torch error.",
  ffmpeg_missing:
    "ffmpeg is not on PATH in the backend image. Rebuild — the light backend installs it by default.",
  ffprobe_missing:
    "ffprobe is not on PATH. Install the ffmpeg package (it ships ffprobe).",
};


// ---------------------------------------------------------------------------
// Per-provider test result shape rendered in the UI.
// ---------------------------------------------------------------------------


type TestOutcome =
  | { readonly kind: "idle" }
  | { readonly kind: "running"; readonly startedAt: number }
  | {
      readonly kind: "success";
      readonly httpStatus: number;
      readonly summary: string;
      readonly detail?: unknown;
      readonly artifactId?: string | null;
    }
  | {
      readonly kind: "failure";
      readonly httpStatus: number;
      readonly errorCode?: string | null;
      readonly message: string;
      readonly guidance?: string;
      readonly detail?: unknown;
    };


// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------


export function ProviderTestPanel() {
  const t = useT();
  void t("providers.testProvider");
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<Record<string, TestOutcome>>({});
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    getProviders()
      .then((p) => {
        if (!cancelled) setProviders(p);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

  const setOutcome = useCallback((key: string, outcome: TestOutcome) => {
    setOutcomes((prev) => ({ ...prev, [key]: outcome }));
  }, []);

  // Lookup of provider IDs that appear in any frontend dropdown (i.e.
  // every provider returned by GET /api/v1/providers). Currently every
  // catalog row is selectable; this is a placeholder for a future filter.
  const usedInDropdowns = useMemo(() => {
    const out = new Set<string>();
    if (!providers) return out;
    for (const cat of [
      "llm",
      "tts",
      "video_generator",
      "audio_processor",
      "image_processor",
    ] as ProviderCategory[]) {
      for (const p of providers[cat] ?? []) {
        out.add(`${cat}:${p.provider_id}`);
      }
    }
    return out;
  }, [providers]);

  return (
    <div className={styles.panel}>
      <div className={styles.toolbar}>
        <span className={styles.head}>{t("providers.test1Title")}</span>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={() => setRefreshTick((n) => n + 1)}
          title={t("providers.refreshCatalog")}
        >
          {t("providers.refreshAction")}
        </button>
      </div>
      <p className={styles.intro}>
        {t("providers.diagnosticsIntro")}{" "}
        {t("providers.backendLabel")}: <code>{getActiveApiBaseUrl()}</code>
      </p>

      {loadError && (
        <p className={styles.error}>
          {t("providers.failedToLoad", { detail: loadError })}
        </p>
      )}

      {providers && (
        <>
          <CategorySection
            title={t("providers.categoryLlm")}
            category="llm"
            providers={providers.llm ?? []}
            outcomes={outcomes}
            setOutcome={setOutcome}
            usedInDropdowns={usedInDropdowns}
            test={(p) => runScriptTest(p, setOutcome)}
          />
          <CategorySection
            title={t("providers.categoryTts")}
            category="tts"
            providers={providers.tts ?? []}
            outcomes={outcomes}
            setOutcome={setOutcome}
            usedInDropdowns={usedInDropdowns}
            test={(p) => runTtsTest(p, setOutcome)}
          />
          <CategorySection
            title={t("providers.categoryVideo")}
            category="video_generator"
            providers={providers.video_generator ?? []}
            outcomes={outcomes}
            setOutcome={setOutcome}
            usedInDropdowns={usedInDropdowns}
            test={(p) => runVideoReadinessTest(p, setOutcome)}
            footnote={t("providers.videoReadinessFootnote")}
          />
          <CategorySection
            title={t("providers.categoryAudioProcessor")}
            category="audio_processor"
            providers={providers.audio_processor ?? []}
            outcomes={outcomes}
            setOutcome={setOutcome}
            usedInDropdowns={usedInDropdowns}
            test={(p) => runMetadataOnlyTest(p, setOutcome)}
          />
          <CategorySection
            title={t("providers.categoryImageProcessor")}
            category="image_processor"
            providers={providers.image_processor ?? []}
            outcomes={outcomes}
            setOutcome={setOutcome}
            usedInDropdowns={usedInDropdowns}
            test={(p) => runMetadataOnlyTest(p, setOutcome)}
          />
        </>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Category section + provider row
// ---------------------------------------------------------------------------


interface CategorySectionProps {
  readonly title: string;
  readonly category: ProviderCategory;
  readonly providers: readonly ProviderInfo[];
  readonly outcomes: Record<string, TestOutcome>;
  readonly setOutcome: (key: string, outcome: TestOutcome) => void;
  readonly usedInDropdowns: ReadonlySet<string>;
  readonly test: (p: ProviderInfo) => Promise<void>;
  readonly footnote?: string;
}


function CategorySection({
  title,
  category,
  providers,
  outcomes,
  usedInDropdowns,
  test,
  footnote,
}: CategorySectionProps) {
  return (
    <section className={styles.section}>
      <header className={styles.sectionHead}>
        <h3>{title}</h3>
        <span className={styles.count}>{providers.length}</span>
      </header>
      {providers.length === 0 ? (
        <p className={styles.empty}>
          This category is empty. The provider registry or frontend mapping
          may be broken.
        </p>
      ) : (
        <ul className={styles.list}>
          {providers.map((p) => {
            const key = `${category}:${p.provider_id}`;
            return (
              <li key={key} className={styles.item}>
                <ProviderRow
                  provider={p}
                  category={category}
                  outcome={outcomes[key] ?? { kind: "idle" }}
                  inDropdown={usedInDropdowns.has(key)}
                  onTest={() => test(p)}
                />
              </li>
            );
          })}
        </ul>
      )}
      {footnote && <p className={styles.footnote}>{footnote}</p>}
    </section>
  );
}


interface ProviderRowProps {
  readonly provider: ProviderInfo;
  readonly category: ProviderCategory;
  readonly outcome: TestOutcome;
  readonly inDropdown: boolean;
  readonly onTest: () => void;
}


function ProviderRow({
  provider,
  category,
  outcome,
  inDropdown,
  onTest,
}: ProviderRowProps) {
  const bucket = _STATUS_BUCKET[provider.status] ?? "muted";
  const isRunning = outcome.kind === "running";
  return (
    <>
      <div className={styles.row}>
        <span className={`${styles.statusDot} ${styles[`statusDot-${bucket}`]}`} />
        <div className={styles.titleCol}>
          <span className={styles.providerLabel}>{provider.label}</span>
          <code className={styles.providerId}>{provider.provider_id}</code>
        </div>
        <button
          type="button"
          className={styles.testBtn}
          disabled={isRunning}
          onClick={onTest}
          title={`Test ${provider.label}`}
        >
          {isRunning ? "Testing…" : "Test"}
        </button>
      </div>
      <div className={styles.metaRow}>
        <span className={`${styles.statusBadge} ${styles[`badge-${bucket}`]}`}>
          {provider.status.replace(/_/g, " ")}
        </span>
        <span className={styles.metaTag}>{category}</span>
        <span className={styles.metaTag}>{provider.local_or_external}</span>
        <span className={styles.metaTag}>{provider.backend_type || "—"}</span>
        {provider.default_model && (
          <span className={styles.metaTag}>model={provider.default_model}</span>
        )}
        {provider.requires_gpu && <span className={styles.flagGpu}>GPU</span>}
        {provider.requires_network && (
          <span className={styles.flagNet}>network</span>
        )}
        {provider.requires_model_files && (
          <span className={styles.flagWeights}>weights</span>
        )}
        {provider.healthcheck_available && (
          <span className={styles.metaTag}>healthcheck</span>
        )}
        {provider.is_custom && (
          <span className={styles.flagCustom}>custom · metadata</span>
        )}
        {inDropdown && (
          <span className={styles.metaTag}>used in dropdowns</span>
        )}
      </div>
      {provider.notes && <p className={styles.notes}>{provider.notes}</p>}
      {provider.docs_url && (
        <p className={styles.docsRow}>
          docs:{" "}
          <code>{provider.docs_url}</code>
        </p>
      )}
      <TestResult outcome={outcome} />
    </>
  );
}


function TestResult({ outcome }: { readonly outcome: TestOutcome }) {
  if (outcome.kind === "idle") return null;
  if (outcome.kind === "running") {
    return (
      <p className={styles.resultRunning}>
        Testing… started {new Date(outcome.startedAt).toLocaleTimeString()}
      </p>
    );
  }
  if (outcome.kind === "success") {
    return (
      <div className={styles.resultOk}>
        <strong>OK</strong> · HTTP {outcome.httpStatus}
        <div className={styles.resultSummary}>{outcome.summary}</div>
        {outcome.artifactId && (
          <div className={styles.resultArtifact}>
            <code>artifact={outcome.artifactId}</code>
            <a
              className={styles.playLink}
              href={artifactContentUrl(outcome.artifactId)}
              target="_blank"
              rel="noopener noreferrer"
            >
              ▶ open
            </a>
          </div>
        )}
        {outcome.detail !== undefined && (
          <details className={styles.detailDrawer}>
            <summary>raw response</summary>
            <pre>{JSON.stringify(outcome.detail, null, 2)}</pre>
          </details>
        )}
      </div>
    );
  }
  // failure
  return (
    <div className={styles.resultErr}>
      <strong>FAIL</strong> · HTTP {outcome.httpStatus}
      {outcome.errorCode && (
        <code className={styles.errorCode}>{outcome.errorCode}</code>
      )}
      <div className={styles.resultSummary}>{outcome.message}</div>
      {outcome.guidance && (
        <div className={styles.resultGuide}>→ {outcome.guidance}</div>
      )}
      {outcome.detail !== undefined && (
        <details className={styles.detailDrawer}>
          <summary>raw response</summary>
          <pre>{JSON.stringify(outcome.detail, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Per-category test runners
// ---------------------------------------------------------------------------


function _logStarted(category: string, providerId: string, endpoint: string) {
  const startedAt = Date.now();
  logBus.emit({
    source: "frontend",
    level: "info",
    message: `provider test started: ${category}/${providerId}`,
    meta: { category, provider_id: providerId, endpoint, started_at: startedAt },
  });
  return startedAt;
}


function _logFinished(
  category: string,
  providerId: string,
  endpoint: string,
  outcome: { ok: boolean; httpStatus: number; errorCode?: string | null; duration: number },
): void {
  logBus.emit({
    source: "frontend",
    level: outcome.ok ? "success" : "warning",
    message: outcome.ok
      ? `provider test succeeded: ${category}/${providerId}`
      : `provider test failed: ${category}/${providerId}`,
    meta: {
      category,
      provider_id: providerId,
      endpoint,
      http_status: outcome.httpStatus,
      error_code: outcome.errorCode ?? null,
      duration_ms: outcome.duration,
    },
  });
}


type SetOutcome = (key: string, outcome: TestOutcome) => void;


async function runScriptTest(p: ProviderInfo, setOutcome: SetOutcome): Promise<void> {
  const key = `llm:${p.provider_id}`;
  const endpoint = "/api/v1/script/generate";
  const startedAt = _logStarted("llm", p.provider_id, endpoint);
  setOutcome(key, { kind: "running", startedAt });

  const start = Date.now();
  try {
    const res = await generateScript({
      brief: "Short provider communication test. Generate one concise sentence.",
      target_duration_seconds: 10,
      provider_id: p.provider_id,
    });
    const duration = Date.now() - start;
    if (res.ok) {
      const v = res.value;
      const preview = (v.hook || v.full_script || "").slice(0, 160);
      setOutcome(key, {
        kind: "success",
        httpStatus: 200,
        summary: `provider=${v.provider_id} model=${v.model} preview="${preview}…"`,
        detail: v,
      });
      _logFinished("llm", p.provider_id, endpoint, {
        ok: true,
        httpStatus: 200,
        duration,
      });
    } else {
      const err = res.error;
      setOutcome(key, {
        kind: "failure",
        httpStatus: res.httpStatus,
        errorCode: err.code,
        message: err.message,
        guidance: err.code ? _ERROR_GUIDE[err.code] : undefined,
        detail: err,
      });
      _logFinished("llm", p.provider_id, endpoint, {
        ok: false,
        httpStatus: res.httpStatus,
        errorCode: err.code,
        duration,
      });
    }
  } catch (exc) {
    const duration = Date.now() - start;
    const message = humanizeApiDetail(
      exc instanceof Error ? exc.message : String(exc),
    );
    setOutcome(key, {
      kind: "failure",
      httpStatus: 0,
      message,
    });
    _logFinished("llm", p.provider_id, endpoint, {
      ok: false,
      httpStatus: 0,
      duration,
    });
  }
}


async function runTtsTest(p: ProviderInfo, setOutcome: SetOutcome): Promise<void> {
  const key = `tts:${p.provider_id}`;
  const endpoint = "/api/v1/tts/generate";
  const startedAt = _logStarted("tts", p.provider_id, endpoint);
  setOutcome(key, { kind: "running", startedAt });

  const start = Date.now();
  try {
    const res = await generateTts({
      script_text: "This is a short text to speech provider test.",
      tts_provider_id: p.provider_id,
      output_format: "wav",
    });
    const duration = Date.now() - start;
    if (res.ok) {
      const v = res.value;
      setOutcome(key, {
        kind: "success",
        httpStatus: 201,
        summary: `provider=${v.provider_id} voice=${v.voice_id} duration=${v.duration_seconds.toFixed(2)}s`,
        artifactId: v.artifact_id,
        detail: v,
      });
      _logFinished("tts", p.provider_id, endpoint, {
        ok: true,
        httpStatus: 201,
        duration,
      });
    } else {
      const err = res.error;
      setOutcome(key, {
        kind: "failure",
        httpStatus: res.httpStatus,
        errorCode: err.code,
        message: err.message,
        guidance: err.code ? _ERROR_GUIDE[err.code] : undefined,
        detail: err,
      });
      _logFinished("tts", p.provider_id, endpoint, {
        ok: false,
        httpStatus: res.httpStatus,
        errorCode: err.code,
        duration,
      });
    }
  } catch (exc) {
    const duration = Date.now() - start;
    const message = humanizeApiDetail(
      exc instanceof Error ? exc.message : String(exc),
    );
    setOutcome(key, {
      kind: "failure",
      httpStatus: 0,
      message,
    });
    _logFinished("tts", p.provider_id, endpoint, {
      ok: false,
      httpStatus: 0,
      duration,
    });
  }
}


async function runVideoReadinessTest(
  p: ProviderInfo,
  setOutcome: SetOutcome,
): Promise<void> {
  const key = `video_generator:${p.provider_id}`;
  const endpoint = `/api/v1/providers/video_generator/${p.provider_id}`;
  const startedAt = _logStarted("video_generator", p.provider_id, endpoint);
  setOutcome(key, { kind: "running", startedAt });

  const start = Date.now();
  try {
    // allow-raw-fetch: this diagnostic panel needs the raw Response so
    // it can render httpStatus + body for any provider URL the operator
    // points at, including ad-hoc custom-provider hosts that the
    // structured lib/api.ts client doesn't know about.
    const r = await fetch(`${getActiveApiBaseUrl()}${endpoint}`);
    const duration = Date.now() - start;
    const body = await r.json().catch(() => null);
    if (r.ok && body) {
      const info = body as ProviderInfo;
      const summary = [
        `status=${info.status}`,
        info.requires_gpu ? "GPU" : "",
        info.requires_model_files ? "weights" : "",
      ]
        .filter(Boolean)
        .join(" · ");
      setOutcome(key, {
        kind: "success",
        httpStatus: r.status,
        summary,
        detail: info,
      });
      _logFinished("video_generator", p.provider_id, endpoint, {
        ok: true,
        httpStatus: r.status,
        duration,
      });
    } else {
      setOutcome(key, {
        kind: "failure",
        httpStatus: r.status,
        message:
          body && typeof body === "object" && "detail" in body
            ? humanizeApiDetail(body)
            : `HTTP ${r.status}`,
        detail: body,
      });
      _logFinished("video_generator", p.provider_id, endpoint, {
        ok: false,
        httpStatus: r.status,
        duration,
      });
    }
  } catch (exc) {
    const duration = Date.now() - start;
    setOutcome(key, {
      kind: "failure",
      httpStatus: 0,
      message: exc instanceof Error ? exc.message : String(exc),
    });
    _logFinished("video_generator", p.provider_id, endpoint, {
      ok: false,
      httpStatus: 0,
      duration,
    });
  }
}


async function runMetadataOnlyTest(
  p: ProviderInfo,
  setOutcome: SetOutcome,
): Promise<void> {
  const key = `${p.category}:${p.provider_id}`;
  const endpoint = `/api/v1/providers/${p.category}/${p.provider_id}`;
  const startedAt = _logStarted(p.category, p.provider_id, endpoint);
  setOutcome(key, { kind: "running", startedAt });

  const start = Date.now();
  try {
    // allow-raw-fetch: this diagnostic panel needs the raw Response so
    // it can render httpStatus + body for any provider URL the operator
    // points at, including ad-hoc custom-provider hosts that the
    // structured lib/api.ts client doesn't know about.
    const r = await fetch(`${getActiveApiBaseUrl()}${endpoint}`);
    const duration = Date.now() - start;
    const body = await r.json().catch(() => null);
    if (r.ok && body) {
      const info = body as ProviderInfo;
      setOutcome(key, {
        kind: "success",
        httpStatus: r.status,
        summary: `status=${info.status}${info.notes ? " · " + info.notes : ""}`,
        detail: info,
      });
      _logFinished(p.category, p.provider_id, endpoint, {
        ok: true,
        httpStatus: r.status,
        duration,
      });
    } else {
      setOutcome(key, {
        kind: "failure",
        httpStatus: r.status,
        message: humanizeApiDetail(body ?? `HTTP ${r.status}`),
        detail: body,
      });
      _logFinished(p.category, p.provider_id, endpoint, {
        ok: false,
        httpStatus: r.status,
        duration,
      });
    }
  } catch (exc) {
    const duration = Date.now() - start;
    setOutcome(key, {
      kind: "failure",
      httpStatus: 0,
      message: exc instanceof Error ? exc.message : String(exc),
    });
    _logFinished(p.category, p.provider_id, endpoint, {
      ok: false,
      httpStatus: 0,
      duration,
    });
  }
}
