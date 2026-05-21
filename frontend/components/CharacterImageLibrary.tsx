"use client";

// Phase 12 — Character image library.
//
// Operator workflow:
//   1. Pick provider + write prompt → Generate
//   2. Accept / reject the result
//   3. Promote an accepted image to "main reference" so subsequent
//      generations can use it as image-to-image conditioning
//      (when the provider supports it).

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { AuthImage } from "@/components/AuthImage";
import { HelpHint } from "@/components/HelpHint";
import { ProviderStatusBadge } from "@/components/ProviderStatusBadge";
import {
  characterImageContentUrl,
  deleteCharacterImage,
  generateCharacterImage,
  generateConsistentImage,
  generateInitialImage,
  listCharacterImages,
  setCharacterImageStatus,
  type CharacterImageGenerateRequest,
  type CharacterImageResponse,
  type CharacterResponse,
  type GenerateConsistentRequest,
} from "@/lib/characters";
import { useT } from "@/lib/i18n/LanguageContext";
import * as api from "@/lib/api";
import type { ProviderInfo, ProvidersResponse } from "@/lib/types";

interface Props {
  readonly character: CharacterResponse;
  readonly onReload: () => Promise<void> | void;
}

export function CharacterImageLibrary({ character, onReload }: Props) {
  const t = useT();
  const [providers, setProviders] = useState<readonly ProviderInfo[]>([]);
  const [images, setImages] = useState<readonly CharacterImageResponse[]>([]);
  const [providerId, setProviderId] = useState<string>(
    character.default_image_provider_id || "flux_local",
  );
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [seed, setSeed] = useState<string>("");
  // Phase 17H — implicitly true when the character has a master
  // reference (face_locked). Backend forces img2img regardless, but
  // sending the flag aligns the UI prompt label.
  const useMainRef = Boolean(character.main_reference_image_id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progressLines, setProgressLines] = useState<string[]>([]);
  // Phase 12 — generation controls live in a "+ Imagine Nouă" modal so the
  // gallery itself shows only images + image actions.
  const [showGen, setShowGen] = useState(false);

  const reloadImages = async () => {
    try {
      const r = await listCharacterImages(character.id);
      setImages(r.items);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const pr: ProvidersResponse = await api.getProviders();
        if (cancelled) return;
        setProviders(pr.image_generator ?? []);
      } catch (err) {
        if (cancelled) return;
        setError((err as Error).message);
      }
    };
    void load();
    void reloadImages();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [character.id]);

  const pickedProvider = useMemo(
    () => providers.find((p) => p.provider_id === providerId),
    [providers, providerId],
  );

  const handleGenerate = async () => {
    setBusy(true);
    setError(null);
    setProgressLines([
      `▸ ${new Date().toLocaleTimeString()} — pornit (provider=${providerId}, mode=${useMainRef ? "img2img" : "txt2img"})`,
    ]);
    // Phase 15G — poll backend logs filtered for this character_id while
    // the request is in flight. Shows the operator exactly where the
    // backend is in the pipeline (translate → dispatch → wrapper → done).
    let lastSeen = 0;
    let cancelled = false;
    const pollLogs = async () => {
      try {
        const resp = await api.getBackendLogs({ since_seq: lastSeen, limit: 50 });
        if (cancelled) return;
        const matches = resp.entries.filter(
          (e) =>
            e.message.includes(character.id)
            || (e.message.includes("characters.image") || e.message.includes("characters.generate_image"))
            || e.logger.includes("character_image_service"),
        );
        if (matches.length > 0) {
          lastSeen = Math.max(lastSeen, ...matches.map((e) => e.seq));
          setProgressLines((prev) => [
            ...prev,
            ...matches.map((e) => `▸ ${new Date(e.ts * 1000).toLocaleTimeString()} [${e.level}] ${e.message}`),
          ]);
        }
        // Always advance lastSeen so future polls only fetch new entries
        lastSeen = Math.max(lastSeen, resp.latest_seq);
      } catch {
        /* silent — main request is the source of truth */
      }
    };
    const pollId = window.setInterval(pollLogs, 1500);
    void pollLogs();
    // try/finally guarantees the log poller is ALWAYS stopped — even if the
    // generation throws (timeout/network/429). Without this the interval
    // leaked and kept hammering the logs endpoint every 1.5s (looked like a loop).
    try {
      const body: CharacterImageGenerateRequest = {
        prompt: prompt || null,
        negative_prompt: negativePrompt || null,
        provider_id: providerId,
        seed: seed ? Number(seed) : null,
        use_main_reference: useMainRef,
      };
      const result = await generateCharacterImage(character.id, body);
      if (!result.ok) {
        const errKey =
          result.error.error_code === "provider_not_configured"
            ? "providerNotConfigured"
            : result.error.error_code === "provider_not_implemented"
            ? "providerNotImplemented"
            : result.error.error_code === "runtime_missing"
            ? "runtimeMissing"
            : "genericFailure";
        const msg =
          result.error.error_code === "circuit_open"
            ? result.error.detail
            : errKey === "genericFailure"
            ? t("characters.images.genericFailure", { detail: result.error.detail })
            : t(`characters.images.${errKey}`, { provider: providerId });
        setError(msg);
        return;
      }
      await reloadImages();
      await onReload();
      setPrompt("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      cancelled = true;
      window.clearInterval(pollId);
      setBusy(false);
    }
  };

  const [actionBusyId, setActionBusyId] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<Record<string, string>>({});

  const handleAction = async (
    image: CharacterImageResponse,
    action:
      | "accept"
      | "reject"
      | "set-main-reference"
      | "set-full-body-reference"
      | "archive",
  ) => {
    setActionBusyId(image.id);
    setError(null);
    try {
      await setCharacterImageStatus(character.id, image.id, action);
      setActionFeedback((f) => ({ ...f, [image.id]: `✓ ${action}` }));
      await reloadImages();
      await onReload();
      // Clear after 2s.
      window.setTimeout(() => {
        setActionFeedback((f) => {
          const copy = { ...f };
          delete copy[image.id];
          return copy;
        });
      }, 2500);
    } catch (err) {
      const msg = (err as Error).message;
      setError(msg);
      setActionFeedback((f) => ({ ...f, [image.id]: `✗ ${msg}` }));
    } finally {
      setActionBusyId(null);
    }
  };

  const handleDelete = async (image: CharacterImageResponse) => {
    if (!window.confirm(t("characters.images.confirmDelete"))) return;
    setActionBusyId(image.id);
    setError(null);
    try {
      await deleteCharacterImage(character.id, image.id);
      await reloadImages();
      await onReload();
    } catch (err) {
      const msg = (err as Error).message;
      setError(msg);
      setActionFeedback((f) => ({ ...f, [image.id]: `✗ ${msg}` }));
    } finally {
      setActionBusyId(null);
    }
  };

  return (
    <div className="image-library">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h3 style={{ marginBottom: 2 }}>
            {t("characters.images.gallery")}
            <HelpHint slug="character-image-library" />
          </h3>
          <p className="muted" style={{ fontSize: 12, margin: 0 }}>
            Imaginile de referință și variațiile vizuale ale personajului.
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setShowGen(true)}>
          + Imagine Nouă
        </button>
      </div>

      {showGen && (
      <div className="modal-overlay" onClick={() => setShowGen(false)}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0 }}>Generează imagine nouă pentru {character.display_name || character.name}</h3>
        <button type="button" className="btn" onClick={() => setShowGen(false)}>Părăsește</button>
      </div>
      <div className="card" style={{ marginBottom: 16, marginTop: 12 }}>
        <label className="form-row">
          <span>
            {t("characters.images.provider")}
            <HelpHint slug="character-image-provider" small />
          </span>
          <select value={providerId} onChange={(e) => setProviderId(e.target.value)}>
            {providers.map((p) => (
              <option key={p.provider_id} value={p.provider_id}>
                {p.label}
              </option>
            ))}
          </select>
          {pickedProvider && (
            <ProviderStatusBadge
              status={pickedProvider.status}
              label={t(`providerStatus.${pickedProvider.status}`)}
              notes={pickedProvider.notes}
              inline
            />
          )}
        </label>
        {/* Phase 15G — full-width stacked prompt blocks */}
        <div
          style={{
            display: "flex", flexDirection: "column", gap: 4,
            marginTop: 12,
          }}
        >
          <label
            style={{ fontWeight: 600, color: "var(--text)" }}
            title={t("characters.images.promptHint")}
          >
            {useMainRef
              ? t("characters.images.promptSceneOnly")
              : t("characters.images.prompt")}{" "}
            <small className="muted" style={{ fontWeight: 400 }}>
              ({useMainRef
                ? t("characters.images.promptSceneShortHint")
                : t("characters.images.promptShortHint")})
            </small>
          </label>
          <textarea
            rows={4}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={useMainRef
              ? t("characters.images.promptScenePlaceholder")
              : t("characters.images.promptPlaceholder")}
            title={t("characters.images.promptHint")}
            style={{
              width: "100%", boxSizing: "border-box",
              padding: "10px", fontFamily: "inherit",
              border: "1px solid var(--border)", borderRadius: 6,
              background: "var(--background)", color: "var(--text)",
              resize: "vertical", minHeight: 90,
            }}
          />
        </div>

        <div
          style={{
            display: "flex", flexDirection: "column", gap: 4,
            marginTop: 12,
          }}
        >
          <label
            style={{ fontWeight: 600, color: "var(--text)" }}
            title={t("characters.images.negativePromptHint")}
          >
            {t("characters.images.negativePrompt")}{" "}
            <small className="muted" style={{ fontWeight: 400 }}>
              ({t("characters.images.negativePromptShortHint")})
            </small>
          </label>
          <textarea
            rows={3}
            value={negativePrompt}
            onChange={(e) => setNegativePrompt(e.target.value)}
            placeholder={t("characters.images.negativePromptPlaceholder")}
            title={t("characters.images.negativePromptHint")}
            style={{
              width: "100%", boxSizing: "border-box",
              padding: "10px", fontFamily: "inherit",
              border: "1px solid var(--border)", borderRadius: 6,
              background: "var(--background)", color: "var(--text)",
              resize: "vertical", minHeight: 70,
            }}
          />
        </div>

        {character.main_reference_image_id && (
          /* Phase 17H — informational notice. Backend enforces img2img
             with the character's locked master face for every generation
             in this profile, regardless of any client flag. */
          <div
            style={{
              padding: "10px 14px", marginTop: 12, marginBottom: 4,
              borderLeft: "3px solid var(--accent, #4a90e2)",
              borderRadius: 4,
              background: "rgba(74, 144, 226, 0.08)",
              fontSize: 13, color: "var(--text)",
              lineHeight: 1.45,
            }}
          >
            <strong>★ {t("characters.images.autoFaceLocked")}</strong>
            <br />
            <span className="muted" style={{ fontSize: 12 }}>
              {t("characters.images.autoFaceLockedHint")}
            </span>
          </div>
        )}

        {/* Seed + Generate button on same row, seed LEFT */}
        <div
          style={{
            display: "flex", alignItems: "flex-end", gap: 12,
            marginTop: 16, flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label
              htmlFor="img-gen-seed"
              style={{ fontSize: "0.9em", color: "var(--text)" }}
            >
              {t("characters.images.seed")}
            </label>
            <input
              id="img-gen-seed"
              type="number"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              placeholder="—"
              style={{
                width: 120, padding: "8px 10px",
                border: "1px solid var(--border)", borderRadius: 6,
                background: "var(--background)", color: "var(--text)",
                fontFamily: "ui-monospace, monospace",
              }}
            />
          </div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleGenerate}
            disabled={busy || !providerId}
            style={{ height: 40, padding: "0 24px", fontSize: "1em" }}
          >
            {busy ? t("characters.images.generating") : t("characters.images.generate")}
          </button>
        </div>

        {/* Phase 15G — live progress log during generation */}
        {(busy || progressLines.length > 0) && (
          <div
            style={{
              marginTop: 12, padding: "10px 12px",
              border: "1px solid var(--border)", borderRadius: 6,
              background: "var(--background)",
              maxHeight: 220, overflowY: "auto",
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              fontSize: "0.85em", lineHeight: 1.5,
            }}
          >
            <div style={{
              fontWeight: 600, fontFamily: "inherit",
              marginBottom: 6, color: "var(--text)",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              {busy && (
                <span
                  style={{
                    width: 10, height: 10, borderRadius: "50%",
                    background: "#4a90e2", animation: "pulse 1s infinite",
                  }}
                />
              )}
              {busy
                ? t("characters.images.progressBusy")
                : t("characters.images.progressDone")}
            </div>
            {progressLines.map((line, i) => (
              <div key={i} style={{ color: "var(--text)", whiteSpace: "pre-wrap" }}>
                {line}
              </div>
            ))}
          </div>
        )}
        {error && <p style={{ color: "var(--danger)", marginTop: 8 }}>{error}</p>}
      </div>

      <IdentityGenPanel
        character={character}
        onGenerated={async () => {
          await reloadImages();
          await onReload();
        }}
      />
      </div>
      </div>
      )}

      {images.length === 0 ? (
        <p className="muted">{t("characters.images.noImages")}</p>
      ) : (
        <div className="imglib-grid">
          {(() => {
            // Face reference first, full-body reference second, rest after.
            const face = images.find((i) => i.id === character.main_reference_image_id);
            const body = images.find((i) => i.id === character.full_body_reference_image_id);
            const rest = images.filter(
              (i) => i.id !== character.main_reference_image_id &&
                     i.id !== character.full_body_reference_image_id,
            );
            const ordered = [face, body, ...rest].filter(Boolean) as CharacterImageResponse[];
            return ordered.map((img, idx) => (
              <ImageCard
                key={img.id}
                image={img}
                index={idx + 1}
                character={character}
                onAction={handleAction}
                onDelete={handleDelete}
                busy={actionBusyId === img.id}
                feedback={actionFeedback[img.id]}
              />
            ));
          })()}
        </div>
      )}
    </div>
  );
}

// Image display name — same convention as videos: <Name>.<HH.MM>.<AM|PM>.<YYYY.MM.DD>
function imageDisplayName(character: CharacterResponse, createdAt?: string): string {
  const name = (character.display_name || character.name || "Personaj")
    .replace(/\s+/g, ".").replace(/[^\w.\-]/g, "").replace(/\.{2,}/g, ".").replace(/^\.|\.$/g, "") || "Personaj";
  const d = createdAt ? new Date(createdAt) : new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const h12 = d.getUTCHours() % 12 || 12;
  const ampm = d.getUTCHours() < 12 ? "AM" : "PM";
  return `${name}.${pad(h12)}.${pad(d.getUTCMinutes())}.${ampm}.${d.getUTCFullYear()}.${pad(d.getUTCMonth() + 1)}.${pad(d.getUTCDate())}`;
}

function imageLabel(
  image: CharacterImageResponse, index: number, isMain: boolean, isFullBody: boolean,
): { readonly title: string; readonly sub: string } {
  if (isMain) return {
    title: `Imagine ${index} — Imagine față de referință`,
    sub: "Referință principală pentru trăsăturile feței, expresie și identitate vizuală.",
  };
  if (isFullBody) return {
    title: `Imagine ${index} — Imagine corp de referință`,
    sub: "Referință principală pentru proporții, postură, stil vestimentar și aspect general.",
  };
  return { title: `Imagine ${index} — Variație`, sub: "" };
}

function ImageCard({
  image,
  index,
  character,
  onAction,
  onDelete,
  busy,
  feedback,
}: {
  readonly image: CharacterImageResponse;
  readonly index: number;
  readonly character: CharacterResponse;
  readonly onAction: (
    image: CharacterImageResponse,
    action:
      | "accept"
      | "reject"
      | "set-main-reference"
      | "set-full-body-reference"
      | "archive",
  ) => void;
  readonly onDelete: (image: CharacterImageResponse) => void;
  readonly busy?: boolean;
  readonly feedback?: string;
}) {
  const t = useT();
  const isMain = character.main_reference_image_id === image.id;
  const isFullBody = character.full_body_reference_image_id === image.id;
  const label = imageLabel(image, index, isMain, isFullBody);
  return (
    <div className={`imglib-card${isMain || isFullBody ? " imglib-ref" : ""}`}>
      <AuthImage
        src={characterImageContentUrl(character.id, image.id)}
        alt={label.title}
        style={{ width: "100%", height: "auto", borderRadius: 6 }}
      />
      <div>
        {/* Video-style image name: <Name>.<HH.MM>.<AM|PM>.<YYYY.MM.DD>. */}
        <p className="imglib-desc" style={{ fontFamily: "var(--mono-stack)", fontSize: 12 }}>
          <strong>{imageDisplayName(character, image.created_at)}</strong>
        </p>
        <p className="imglib-desc"><strong>{label.title}</strong></p>
        {label.sub && <p className="muted" style={{ fontSize: 12, margin: "0 0 4px" }}>{label.sub}</p>}
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", margin: "4px 0" }}>
          {isMain && <span className="badge badge-success">{t("characters.images.mainReferenceBadge")}</span>}
          {isFullBody && <span className="badge badge-success">{t("characters.images.fullBodyReferenceBadge")}</span>}
          <span className="badge">{image.status}</span>
          {typeof image.identity_similarity_score === "number" && (
            <span className="badge badge-info">
              {t("characters.images.identityScore", { score: image.identity_similarity_score.toFixed(3) })}
              {image.identity_drift_warning ? " ⚠" : ""}
            </span>
          )}
        </div>
        {/* Raw generation prompt hidden behind a collapsible (not clutter). */}
        {image.prompt && (
          <details style={{ fontSize: 11, margin: "2px 0 6px" }}>
            <summary className="muted" style={{ cursor: "pointer" }}>Detalii prompt</summary>
            <p style={{ fontSize: 11, color: "var(--text-muted)" }}>{image.prompt}</p>
          </details>
        )}
        {/* Phase 17F — when accepted, lock all destructive buttons. */}
        {image.status === "accepted" ? (
          <div
            style={{
              marginTop: 6, padding: "8px 10px", borderRadius: 6,
              background: "rgba(84, 211, 154, 0.12)",
              border: "1px solid #54d39a",
              color: "var(--text)", fontSize: 12, fontWeight: 600,
            }}
            title={t("characters.images.lockedHint")}
          >
            🔒 {t("characters.images.lockedAccepted")}
            {isMain && (
              <span style={{ marginLeft: 6 }}>★ {t("characters.images.mainReferenceBadge")}</span>
            )}
          </div>
        ) : (
          <div className="imglib-actions">
            <button type="button" className="btn btn-secondary" onClick={() => onAction(image, "accept")} disabled={busy}>
              {busy ? "…" : t("characters.images.accept")}
            </button>
            <button type="button" className="btn" onClick={() => onAction(image, "reject")} disabled={busy}>
              {busy ? "…" : t("characters.images.reject")}
            </button>
            {!isMain && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => onAction(image, "set-main-reference")}
                disabled={busy}
              >
                {busy ? "…" : t("characters.images.setMainReference")}
              </button>
            )}
            {!isFullBody && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => onAction(image, "set-full-body-reference")}
                disabled={busy}
              >
                {busy ? "…" : t("characters.images.setFullBodyReference")}
              </button>
            )}
            <button type="button" className="btn" onClick={() => onAction(image, "archive")} disabled={busy}>
              {busy ? "…" : t("characters.images.archive")}
            </button>
            <button type="button" className="btn btn-danger" onClick={() => onDelete(image)} disabled={busy}>
              {busy ? "…" : t("characters.images.delete")}
            </button>
          </div>
        )}
        {feedback && (
          <p
            style={{
              marginTop: 6, fontSize: 12, fontWeight: 600,
              color: feedback.startsWith("✓") ? "#54d39a" : "#ff7878",
            }}
          >
            {feedback}
          </p>
        )}
        {/* Phase 17 — generate video using this image */}
        {(() => {
          const name = (character.display_name ?? character.name ?? "video")
            .replace(/[^a-zA-Z0-9_-]+/g, "_")
            .slice(0, 60);
          const n = (character.video_count ?? 0) + 1;
          const brief = `${name}_video_${n}`;
          return (
            <div className="imglib-actions" style={{ marginTop: 6 }}>
            <Link
              href={`/jobs/new?character_id=${character.id}&brief=${encodeURIComponent(brief)}`}
              className="btn btn-primary imglib-action-wide"
              style={{ textDecoration: "none", background: "var(--accent, #4a90e2)", color: "white" }}
              title="Pipeline-ul video este momentan oprit / va fi activat pe serverul de 128GB. Acest buton pregătește un job video pe baza acestei imagini."
            >
              🎬 Generează video pe baza acestei imagini
            </Link>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

// Phase IG-4 — identity-consistent generation panel. "Initial" proposes a
// first face (text-to-image); "consistent" needs both canonical references.
function IdentityGenPanel({
  character,
  onGenerated,
}: {
  readonly character: CharacterResponse;
  readonly onGenerated: () => Promise<void> | void;
}) {
  const t = useT();
  const hasFace = Boolean(character.main_reference_image_id);
  const hasBody = Boolean(character.full_body_reference_image_id);
  const canConsistent = hasFace && hasBody;

  const [scene, setScene] = useState<GenerateConsistentRequest>({
    scene_prompt: "",
    outfit_prompt: "",
    location_prompt: "",
    season: "",
    time_of_day: "",
    weather: "",
    head_wear: "",
    mood: "",
    pose: "",
    framing: "full body, full length",
    aspect_ratio: "portrait",
    quality_preset: "standard",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  // Extra photographic aspects (no dedicated backend column) — composed into
  // scene_prompt at submit so the prompt stays rich without schema churn.
  const [extras, setExtras] = useState<Record<string, string>>({});
  const setExtra = (k: string, v: string) => setExtras((e) => ({ ...e, [k]: v }));

  const set = (patch: Partial<GenerateConsistentRequest>) =>
    setScene((s) => ({ ...s, ...patch }));

  const run = async (kind: "initial" | "consistent") => {
    setBusy(true);
    setError(null);
    setStatus(t("characters.identity.generating"));
    try {
      if (kind === "initial") {
        await generateInitialImage(character.id, {
          aspect_ratio: scene.aspect_ratio,
          quality_preset: scene.quality_preset,
        });
      } else {
        // Compose the extra aspects + free text into scene_prompt.
        const composedScene = [
          ...Object.values(extras).filter(Boolean),
          (scene.scene_prompt ?? "").trim(),
        ].filter(Boolean).join(", ");
        await generateConsistentImage(character.id, { ...scene, scene_prompt: composedScene });
      }
      setStatus(t("characters.identity.done"));
      await onGenerated();
    } catch (err) {
      setError((err as Error).message);
      setStatus(null);
    } finally {
      setBusy(false);
    }
  };

  // Dropdown of common options + a free-text field for anything custom.
  // Each option is [Romanian label, English value-for-the-prompt].
  const combo = (
    label: string,
    value: string,
    options: readonly (readonly [string, string])[],
    onChange: (v: string) => void,
  ) => {
    const known = options.some(([, v]) => v === value);
    return (
      <div className="gen-field">
        <span className="gen-label">{label}</span>
        <select
          value={known ? value : ""}
          onChange={(e) => onChange(e.target.value)}
          disabled={busy}
        >
          <option value="">—</option>
          {options.map(([ro, v]) => <option key={v} value={v}>{ro}</option>)}
        </select>
        <input
          type="text"
          value={known ? "" : value}
          placeholder="sau scrie liber…"
          onChange={(e) => onChange(e.target.value)}
          disabled={busy}
        />
      </div>
    );
  };

  return (
    <div className="card" style={{ marginTop: 16, padding: 12 }}>
      <h4 style={{ marginTop: 0 }}>{t("characters.identity.title")}</h4>
      <p className="muted" style={{ fontSize: 12 }}>
        {t("characters.identity.help")}
      </p>

      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn"
          onClick={() => run("initial")}
          disabled={busy}
          title={t("characters.identity.initialHint")}
        >
          {t("characters.identity.generateInitial")}
        </button>
        {!canConsistent && (
          <span className="muted" style={{ fontSize: 12 }}>
            {t("characters.identity.needRefs")}
          </span>
        )}
      </div>

      {/* ── Cameră & încadrare ── */}
      <div className="gen-group">Cameră &amp; încadrare</div>
      <div className="gen-field">
        <span className="gen-label">Tip poză</span>
        <select value={scene.framing} onChange={(e) => set({ framing: e.target.value })} disabled={busy} style={{ gridColumn: "2 / span 2" }}>
          <option value="extreme close-up portrait">Prim-plan strâns (față)</option>
          <option value="upper body, medium close-up">Corp superior (bust)</option>
          <option value="half body, waist up">Bust lărgit (până la brâu)</option>
          <option value="three-quarter body, knees up">Trei sferturi (până la genunchi)</option>
          <option value="full body, full length">Corp întreg</option>
          <option value="wide environmental shot, full body">Plan larg (corp + mediu)</option>
        </select>
      </div>
      {combo("Unghi cameră", extras.camera_angle ?? "", [
        ["La nivelul ochilor", "eye-level angle"], ["De jos", "low angle"], ["De sus", "high angle"],
        ["Plonjat (bird's eye)", "birds-eye view"], ["Înclinat (dutch)", "dutch angle"],
      ], (v) => setExtra("camera_angle", v))}
      {combo("Obiectiv", extras.lens ?? "", [
        ["Portret 85mm", "85mm portrait lens, shallow depth of field"], ["50mm", "50mm lens"],
        ["35mm", "35mm lens"], ["Wide 24mm", "24mm wide-angle lens"], ["Tele 135mm", "135mm telephoto, compressed"],
      ], (v) => setExtra("lens", v))}
      {combo("Profunzime câmp", extras.dof ?? "", [
        ["Fundal blurat (bokeh)", "shallow depth of field, creamy bokeh"], ["Tot clar", "deep focus, everything sharp"],
      ], (v) => setExtra("dof", v))}

      {/* ── Scenă & mediu ── */}
      <div className="gen-group">Scenă &amp; mediu</div>
      {combo("Interior/exterior", extras.setting ?? "", [["Interior", "indoor"], ["Exterior", "outdoor"]], (v) => setExtra("setting", v))}
      {combo("Fundal / locație", scene.location_prompt ?? "", [
        ["Studio simplu", "plain studio background"], ["Stradă urbană", "urban street"], ["Parc", "park"],
        ["Birou modern", "modern office"], ["Interior casă", "home interior"], ["Plajă", "beach"],
        ["Munte", "mountains"], ["Cafenea", "cafe"], ["Pădure", "forest"], ["Oraș noaptea", "city at night"],
        ["Bibliotecă", "library"], ["Restaurant", "restaurant"], ["Peisaj natural", "nature landscape"],
      ], (v) => set({ location_prompt: v }))}
      {combo("Anotimp", scene.season ?? "", [
        ["Primăvară", "spring"], ["Vară", "summer"], ["Toamnă", "autumn"], ["Iarnă", "winter"],
      ], (v) => set({ season: v }))}
      {combo("Ora din zi", scene.time_of_day ?? "", [
        ["Dimineață", "morning"], ["Prânz", "midday"], ["După-amiază", "afternoon"],
        ["Seară", "evening"], ["Noapte", "night"], ["Răsărit", "sunrise"], ["Apus", "golden hour sunset"],
      ], (v) => set({ time_of_day: v }))}
      {combo("Vreme / fenomene", scene.weather ?? "", [
        ["Senin", "clear sky"], ["Înnorat", "overcast"], ["Ploaie", "rain"], ["Vânt", "windy, hair moving"],
        ["Ninsoare", "snow"], ["Ceață", "fog"], ["Furtună", "storm"], ["Soare puternic", "bright sunlight"],
      ], (v) => set({ weather: v }))}
      {combo("Iluminare", extras.lighting ?? "", [
        ["Naturală", "natural light"], ["Oră de aur", "warm golden-hour light"], ["Studio soft", "soft studio softbox lighting"],
        ["Dramatică/contrast", "dramatic high-contrast lighting"], ["Contre-jour", "backlight, rim light"],
        ["Neon", "neon lighting"], ["Lumânare", "candlelight, warm"], ["Înnorat difuz", "soft overcast light"],
      ], (v) => setExtra("lighting", v))}
      {combo("Atmosferă", extras.atmosphere ?? "", [
        ["Senină", "serene atmosphere"], ["Dramatică", "dramatic atmosphere"], ["Confortabilă", "cozy atmosphere"],
        ["Energică", "energetic atmosphere"], ["Melancolică", "melancholic atmosphere"], ["Lux/elegant", "luxurious elegant atmosphere"],
      ], (v) => setExtra("atmosphere", v))}

      {/* ── Persoană: expresie & postură ── */}
      <div className="gen-group">Persoană — expresie &amp; postură</div>
      {combo("Stare / expresie", scene.mood ?? "", [
        ["Zâmbet", "smiling"], ["Zâmbet larg", "broad happy smile"], ["Serios", "serious"], ["Trist", "sad"],
        ["Râde", "laughing"], ["Plânge", "crying, teary"], ["Gânditor", "thoughtful"], ["Surprins", "surprised"],
        ["Încrezător", "confident"], ["Calm", "calm, relaxed"], ["Furios", "angry"], ["Visător", "dreamy"], ["Neutru", "neutral expression"],
      ], (v) => set({ mood: v }))}
      {combo("Privire", extras.gaze ?? "", [
        ["Spre cameră", "looking at the camera"], ["În lateral", "looking away to the side"],
        ["În jos", "looking down"], ["În sus", "looking up"], ["Ochii închiși", "eyes closed"],
      ], (v) => setExtra("gaze", v))}
      {combo("Postură", scene.pose ?? "", [
        ["În picioare", "standing"], ["Așezat", "sitting"], ["Mergând", "walking"], ["Sprijinit", "leaning"],
        ["Din profil", "side profile"], ["Trei sferturi", "three-quarter view"], ["Întins", "reclining"],
      ], (v) => set({ pose: v }))}
      {combo("Gesturi / mâini", extras.gesture ?? "", [
        ["Relaxate", "hands relaxed"], ["Brațe încrucișate", "arms crossed"], ["Mână la bărbie", "hand on chin"],
        ["Salută", "waving"], ["Mâini în buzunare", "hands in pockets"], ["Ține un obiect", "holding an object"],
      ], (v) => setExtra("gesture", v))}

      {/* ── Vestimentație & styling ── */}
      <div className="gen-group">Vestimentație &amp; styling</div>
      {combo("Îmbrăcăminte corp", scene.outfit_prompt ?? "", [
        ["Casual", "casual outfit"], ["Business", "business suit"], ["Elegant/seară", "elegant evening dress"],
        ["Smart casual", "smart casual blazer"], ["Sport", "sportswear"], ["Tradițional", "traditional clothing"],
        ["Palton iarnă", "winter coat"], ["Vară lejer", "light summer clothing"], ["Trench", "trench coat"],
      ], (v) => set({ outfit_prompt: v }))}
      {combo("Acoperământ cap", scene.head_wear ?? "", [
        ["Fără", "no headwear"], ["Pălărie", "hat"], ["Șapcă", "cap"], ["Eșarfă/batic", "headscarf"],
        ["Căciulă", "wool beanie"], ["Ochelari", "glasses"], ["Ochelari de soare", "sunglasses"],
      ], (v) => set({ head_wear: v }))}
      {combo("Încălțăminte", extras.footwear ?? "", [
        ["Adidași", "sneakers"], ["Pantofi eleganți", "formal shoes"], ["Cizme", "boots"],
        ["Tocuri", "high heels"], ["Sandale", "sandals"], ["Mocasini", "loafers"],
      ], (v) => setExtra("footwear", v))}
      {combo("Accesorii", extras.accessories ?? "", [
        ["Fără", "no accessories"], ["Colier", "necklace"], ["Cercei", "earrings"], ["Ceas", "wristwatch"],
        ["Eșarfă", "scarf"], ["Geantă", "handbag"], ["Curea", "belt"],
      ], (v) => setExtra("accessories", v))}
      {combo("Machiaj", extras.makeup ?? "", [
        ["Natural", "natural makeup"], ["Fără", "no makeup"], ["Elegant/glam", "glamorous makeup"], ["Îndrăzneț", "bold makeup"],
      ], (v) => setExtra("makeup", v))}
      {combo("Paletă culori ținută", extras.color_palette ?? "", [
        ["Neutre", "neutral tones"], ["Monocrom", "monochrome outfit"], ["Calde", "warm tones"],
        ["Reci", "cool tones"], ["Vibrante", "vibrant colors"], ["Pasteluri", "pastel colors"],
      ], (v) => setExtra("color_palette", v))}

      {/* ── Stil foto & acțiune ── */}
      <div className="gen-group">Stil foto &amp; acțiune</div>
      {combo("Stil fotografic", extras.photo_style ?? "", [
        ["Editorial", "editorial photography"], ["Corporate headshot", "corporate headshot"], ["Fashion", "high-fashion editorial"],
        ["Documentar", "documentary candid"], ["Cinematic", "cinematic film still"], ["Film vintage", "vintage film look"],
        ["Lifestyle", "lifestyle photography"], ["B&W", "black and white photography"],
      ], (v) => setExtra("photo_style", v))}
      {combo("Acțiune", extras.action ?? "", [
        ["Pozează", "posing for the camera"], ["Citește", "reading a book"], ["Lucrează la laptop", "working on a laptop"],
        ["Bea cafea", "drinking coffee"], ["Vorbește la telefon", "talking on the phone"], ["Se plimbă", "walking outdoors"],
        ["Gătește", "cooking"], ["Conduce", "driving"],
      ], (v) => setExtra("action", v))}
      {combo("Recuzită", extras.props ?? "", [
        ["Fără", "no props"], ["Ceașcă cafea", "coffee cup"], ["Carte", "book"], ["Laptop", "laptop"],
        ["Telefon", "smartphone"], ["Umbrelă", "umbrella"], ["Flori", "flowers"], ["Ochelari în mână", "holding glasses"],
      ], (v) => setExtra("props", v))}

      <label className="form-row" style={{ marginTop: 8 }}>
        <span>Descriere suplimentară (opțional)</span>
        <textarea
          value={scene.scene_prompt ?? ""}
          onChange={(e) => set({ scene_prompt: e.target.value })}
          placeholder="Orice detalii relevante care nu sunt acoperite mai sus…"
          rows={3}
          disabled={busy}
          style={{ width: "100%", boxSizing: "border-box" }}
        />
      </label>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="form-row" style={{ margin: 0 }}>
          <span>{t("characters.identity.aspect")}</span>
          <select
            value={scene.aspect_ratio}
            onChange={(e) => set({ aspect_ratio: e.target.value as GenerateConsistentRequest["aspect_ratio"] })}
            disabled={busy}
          >
            <option value="portrait">9:16</option>
            <option value="landscape">16:9</option>
            <option value="square">1:1</option>
          </select>
        </label>
        <label className="form-row" style={{ margin: 0 }}>
          <span>{t("characters.identity.quality")}</span>
          <select
            value={scene.quality_preset}
            onChange={(e) => set({ quality_preset: e.target.value as GenerateConsistentRequest["quality_preset"] })}
            disabled={busy}
          >
            <option value="draft">draft</option>
            <option value="standard">standard</option>
            <option value="high">high</option>
          </select>
        </label>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => run("consistent")}
          disabled={busy || !canConsistent}
          title={canConsistent ? "" : t("characters.identity.needRefs")}
        >
          {t("characters.identity.generateConsistent")}
        </button>
      </div>

      {status && <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>{status}</p>}
      {error && <p style={{ color: "var(--danger)", marginTop: 6 }}>{error}</p>}
    </div>
  );
}
