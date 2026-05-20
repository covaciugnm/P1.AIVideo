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
import { StatusBadge } from "@/components/StatusBadge";
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
  const canActivate = status === "editing";
  const canEdit = status === "active" || status === "retired" || status === "inactive";
  const canRetire = status === "active" || status === "editing";

  return (
    <div>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h1>{character.display_name || character.name}</h1>
          <div className="muted" style={{ fontSize: 12 }}>
            {character.slug} · {t("characters.version", { version: character.version_number })}{" "}
            · <StatusBadge status={character.status} />
          </div>
        </div>
        <Link href="/characters" className="btn">{t("common.back")}</Link>
      </header>

      {/* Phase 23 — lifecycle transition controls. */}
      <div
        className="lifecycle-bar"
        style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}
      >
        <span className="muted" style={{ fontSize: 12 }}>
          {t("characters.lifecycle.label")}:
        </span>
        {canEdit && (
          <button
            type="button"
            className="btn"
            onClick={() => handleTransition("editing")}
            disabled={busy}
          >
            {t("characters.lifecycle.toEditing")}
          </button>
        )}
        {canActivate && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => handleTransition("active")}
            disabled={busy}
          >
            {t("characters.lifecycle.toActive")}
          </button>
        )}
        {canRetire && (
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => handleTransition("retired")}
            disabled={busy}
          >
            {t("characters.lifecycle.toRetired")}
          </button>
        )}
        <button
          type="button"
          className="btn"
          onClick={handleClone}
          disabled={busy}
          title={t("characters.lifecycle.cloneHint")}
        >
          {t("characters.lifecycle.clone")}
        </button>
        {identityLocked && (
          <span className="muted" style={{ fontSize: 12 }}>
            {t("characters.lifecycle.lockedHint")}
          </span>
        )}
      </div>
      {error && <ErrorMessage title={t("common.error")} message={error} />}
      <div className="tabs" style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {(["profile", "images", "videos"] as Tab[]).map((k) => (
          <button
            key={k}
            type="button"
            className={`btn ${tab === k ? "btn-primary" : ""}`}
            onClick={() => setTab(k)}
          >
            {t(`characters.sections.${k === "profile" ? "identity" : k}`)}
          </button>
        ))}
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
