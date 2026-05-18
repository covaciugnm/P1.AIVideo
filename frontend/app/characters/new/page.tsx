"use client";

// Phase 12 — Create new character.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { CharacterForm, makeDefaultFormValue, type CharacterFormValue } from "@/components/CharacterForm";
import { ErrorMessage } from "@/components/ErrorMessage";
import { createCharacter } from "@/lib/characters";
import { useT } from "@/lib/i18n/LanguageContext";

export default function NewCharacterPage() {
  const t = useT();
  const router = useRouter();
  const [value, setValue] = useState<CharacterFormValue>(makeDefaultFormValue());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!value.profile.identity.name.trim()) {
      setError(t("characters.nameLabel") + " *");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await createCharacter({
        profile: value.profile,
        status: value.status,
        default_language: value.default_language || null,
        default_voice_provider_id: value.default_voice_provider_id || null,
        default_image_provider_id: value.default_image_provider_id || null,
      });
      router.push(`/characters/${created.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <header style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h1>{t("characters.addNew")}</h1>
        <Link href="/characters" className="btn">{t("common.cancel")}</Link>
      </header>
      {error && <ErrorMessage title={t("common.error")} message={error} />}
      <CharacterForm value={value} onChange={setValue} />
      <div style={{ marginTop: 16 }}>
        <button type="button" className="btn btn-primary" onClick={handleSubmit} disabled={busy}>
          {busy ? t("common.submitting") : t("common.save")}
        </button>
      </div>
    </div>
  );
}
