"use client";

// Phase 12 — Character profile page (tabbed: Profile / Images / Videos / Settings).

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { CharacterForm, type CharacterFormValue } from "@/components/CharacterForm";
import { CharacterIdentityProfile } from "@/components/CharacterIdentityProfile";
import { CharacterImageLibrary } from "@/components/CharacterImageLibrary";
import { CharacterVideoLinks } from "@/components/CharacterVideoLinks";
import { ErrorMessage } from "@/components/ErrorMessage";
import { LoadingState } from "@/components/LoadingState";
import { useRouter } from "next/navigation";

import {
  type CharacterResponse,
  type CharacterStatus,
  cloneCharacter,
  getCharacter,
  listAvailableVoices,
  transitionCharacterStatus,
  updateCharacter,
} from "@/lib/characters";
import { useT } from "@/lib/i18n/LanguageContext";

type Tab = "profile" | "images" | "videos";

export default function CharacterDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const t = useT();
  const id = params?.id;
  const [character, setCharacter] = useState<CharacterResponse | null>(null);
  const [tab, setTab] = useState<Tab>("profile");
  const [editingProfile, setEditingProfile] = useState(false);
  const [form, setForm] = useState<CharacterFormValue | null>(null);
  const [availableVoices, setAvailableVoices] = useState<readonly string[] | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    if (!id) return;
    try {
      const [r, voices] = await Promise.all([
        getCharacter(id),
        listAvailableVoices(id).catch(() => null),
      ]);
      setCharacter(r);
      setAvailableVoices(voices);
      setForm({
        profile: r.profile,
        status: r.status,
        default_language: r.default_language ?? "",
        default_voice_provider_id: r.default_voice_provider_id ?? "",
        default_image_provider_id: r.default_image_provider_id ?? "",
      });
    } catch (err) {
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleSave = async () => {
    if (!id || !form) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateCharacter(id, {
        profile: form.profile,
        status: form.status,
        default_language: form.default_language || null,
        default_voice_provider_id: form.default_voice_provider_id || null,
        default_image_provider_id: form.default_image_provider_id || null,
      });
      setCharacter(updated);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleTransition = async (next: CharacterStatus) => {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      await transitionCharacterStatus(id, next);
      await reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleClone = async () => {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const clone = await cloneCharacter(id);
      router.push(`/characters/${clone.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  if (!character || !form) {
    return <LoadingState label={t("common.loading")} />;
  }

  // Phase 23 — which lifecycle buttons make sense from the current state.
  const status = character.status;
  const identityLocked = status === "active";
  // One-way lifecycle: editing(draft) → active → retired. The CURRENT state
  // button is green + disabled; the NEXT state button is black + enabled;
  // past-state buttons are hidden. Characters are never deleted (videos
  // depend on them) — they stay retired.
  const isEditing = status === "editing" || status === "draft" || status === "inactive";
  const isActive = status === "active";
  const isRetired = status === "retired";

  return (
    <div>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h1>{character.display_name || character.name}</h1>
        </div>
        <Link href="/characters" className="btn">{t("common.back")}</Link>
      </header>

      {/* Lifecycle: one-way editing → active → retired. Green = current
          state (disabled); black + enabled = the next reachable action;
          past states hidden. Clone is always available. */}
      <div
        className="char-btnrow"
        style={{ marginBottom: 10 }}
      >
        {/* În Editare — visible only while editing (current = green). */}
        {isEditing && (
          <button type="button" className="btn btn-success" disabled>
            {t("characters.lifecycle.stateEditing")}
          </button>
        )}

        {/* Activ — hidden once retired; green when active; action when editing. */}
        {!isRetired && (
          <button
            type="button"
            className={`btn ${isActive ? "btn-success" : ""}`}
            disabled={busy || isActive}
            onClick={() => handleTransition("active")}
          >
            {t("characters.lifecycle.stateActive")}
          </button>
        )}

        {/* Retras — green when retired; action when active; shown-disabled while editing. */}
        <button
          type="button"
          className={`btn ${isRetired ? "btn-success" : ""}`}
          disabled={busy || isRetired || isEditing}
          onClick={() => handleTransition("retired")}
        >
          {t("characters.lifecycle.stateRetired")}
        </button>

        {/* Clonează personajul — always available. */}
        <button
          type="button"
          className="btn"
          onClick={handleClone}
          disabled={busy}
          title={t("characters.lifecycle.cloneHint")}
        >
          {t("characters.lifecycle.clone")}
        </button>
      </div>
      {error && <ErrorMessage title={t("common.error")} message={error} />}
      <div className="char-btnrow" style={{ marginBottom: 16 }}>
        {(() => {
          // Tab gating: Identitate always; Biblioteca only when the character
          // is active (identity completed + activated); Video only after the
          // two reference images (face + full-body) exist.
          const hasBothRefs = !!character.main_reference_image_id && !!character.full_body_reference_image_id;
          const tabEnabled: Record<Tab, boolean> = {
            profile: true,
            images: isActive,
            videos: isActive && hasBothRefs,
          };
          const tabHint: Record<Tab, string> = {
            profile: "",
            images: isActive ? "" : "Activează personajul (completează Identitatea) pentru a debloca biblioteca.",
            videos: tabEnabled.videos ? "" : "Generează cele două imagini de referință (față + corp) pentru a debloca videoul.",
          };
          return (["profile", "images", "videos"] as Tab[]).map((k) => (
            <button
              key={k}
              type="button"
              className={`btn ${tab === k ? "btn-success" : ""}`}
              onClick={() => tabEnabled[k] && setTab(k)}
              disabled={!tabEnabled[k]}
              title={tabHint[k]}
            >
              {t(`characters.sections.${k === "profile" ? "identity" : k}`)}
            </button>
          ));
        })()}
      </div>
      {tab === "profile" && (
        editingProfile ? (
          <>
            <CharacterForm
              value={form}
              onChange={setForm}
              availableVoices={availableVoices}
              identityLocked={identityLocked}
            />
            <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
              <button type="button" className="btn btn-primary"
                onClick={async () => { await handleSave(); setEditingProfile(false); }} disabled={busy}>
                {busy ? t("common.submitting") : t("common.save")}
              </button>
              <button type="button" className="btn" onClick={() => setEditingProfile(false)} disabled={busy}>
                {t("common.cancel")}
              </button>
            </div>
          </>
        ) : (
          <>
            <div style={{ marginBottom: 12 }}>
              <button type="button" className="btn" onClick={() => setEditingProfile(true)}>
                ✎ Editează profil
              </button>
            </div>
            <CharacterIdentityProfile character={character} />
          </>
        )
      )}
      {tab === "images" && (
        <CharacterImageLibrary character={character} onReload={reload} />
      )}
      {tab === "videos" && (
        <>
          <p className="muted" style={{ marginBottom: 8 }}>
            {character.video_count} {t("characters.videosCount").toLowerCase()}
          </p>
          <CharacterVideoLinks characterId={character.id} />
        </>
      )}
    </div>
  );
}
