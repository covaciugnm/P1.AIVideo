"use client";

// Phase 12 — Character profile page (tabbed: Profile / Images / Videos / Settings).

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { CharacterForm, type CharacterFormValue } from "@/components/CharacterForm";
import { CharacterImageLibrary } from "@/components/CharacterImageLibrary";
import { CharacterVideoLinks } from "@/components/CharacterVideoLinks";
import { ErrorMessage } from "@/components/ErrorMessage";
import { LoadingState } from "@/components/LoadingState";
import { StatusBadge } from "@/components/StatusBadge";
import {
  type CharacterResponse,
  getCharacter,
  updateCharacter,
} from "@/lib/characters";
import { useT } from "@/lib/i18n/LanguageContext";

type Tab = "profile" | "images" | "videos" | "settings";

export default function CharacterDetailPage() {
  const params = useParams<{ id: string }>();
  const t = useT();
  const id = params?.id;
  const [character, setCharacter] = useState<CharacterResponse | null>(null);
  const [tab, setTab] = useState<Tab>("profile");
  const [form, setForm] = useState<CharacterFormValue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    if (!id) return;
    try {
      const r = await getCharacter(id);
      setCharacter(r);
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

  if (!character || !form) {
    return <LoadingState label={t("common.loading")} />;
  }

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
      {error && <ErrorMessage title={t("common.error")} message={error} />}
      <div className="tabs" style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {(["profile", "images", "videos", "settings"] as Tab[]).map((k) => (
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
        <>
          <CharacterForm value={form} onChange={setForm} />
          <div style={{ marginTop: 16 }}>
            <button type="button" className="btn btn-primary" onClick={handleSave} disabled={busy}>
              {busy ? t("common.submitting") : t("common.save")}
            </button>
          </div>
        </>
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
      {tab === "settings" && (
        <>
          <CharacterForm value={form} onChange={setForm} />
          <div style={{ marginTop: 16 }}>
            <button type="button" className="btn btn-primary" onClick={handleSave} disabled={busy}>
              {busy ? t("common.submitting") : t("common.save")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
