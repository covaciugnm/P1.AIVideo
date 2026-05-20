"use client";

// Phase 12 — Characters tab landing page (list + add new).

import Link from "next/link";
import { useEffect, useState } from "react";

import { ErrorMessage } from "@/components/ErrorMessage";
import { HelpHint } from "@/components/HelpHint";
import { LoadingState } from "@/components/LoadingState";
import { StatusBadge } from "@/components/StatusBadge";
import {
  type CharacterSummary,
  deleteCharacter,
  listCharacters,
} from "@/lib/characters";
import { useT } from "@/lib/i18n/LanguageContext";

export default function CharactersPage() {
  const t = useT();
  const [items, setItems] = useState<readonly CharacterSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [busyDeleteId, setBusyDeleteId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await listCharacters();
      setItems(r.items);
      setTotal(r.total);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
  }, []);

  const handleDelete = async (id: string) => {
    setBusyDeleteId(id);
    try {
      await deleteCharacter(id);
      await reload();
    } catch (err) {
      setError(err as Error);
    } finally {
      setBusyDeleteId(null);
      setConfirmDeleteId(null);
    }
  };

  return (
    <div>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1>
          <span title={t("characters.pageHelp")} style={{ cursor: "help" }}>
            {t("characters.title")}
          </span>
          <HelpHint slug="characters" />
        </h1>
        <Link href="/characters/new" className="btn btn-primary">
          {t("characters.addNew")}
        </Link>
      </header>
      {error && (
        <ErrorMessage
          title={t("jobs.failedToLoad")}
          message={error.message}
        />
      )}
      {loading && items === null && <LoadingState label={t("common.loading")} />}
      {items !== null && items.length === 0 && (
        <div className="card">
          <p className="muted">{t("characters.empty")}</p>
        </div>
      )}
      {items !== null && items.length > 0 && (
        <div className="card">
          <table className="simple">
            <thead>
              <tr>
                <th>{t("characters.nameLabel")}</th>
                <th>{t("characters.statusLabel")}</th>
                <th>{t("characters.languageLabel")}</th>
                <th>{t("characters.imagesCount")}</th>
                <th>{t("characters.videosCount")}</th>
                <th>{t("common.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link href={`/characters/${c.id}`}><strong>{c.display_name || c.name}</strong></Link>
                    <div className="muted" style={{ fontSize: 11 }}>
                      {c.slug} · {t("characters.version", { version: c.version_number })}
                    </div>
                  </td>
                  <td><StatusBadge status={c.status} /></td>
                  <td>{c.default_language ?? "—"}</td>
                  <td>{c.image_count}</td>
                  <td>{c.video_count}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <Link href={`/characters/${c.id}`} className="btn btn-secondary">
                      {t("characters.actions.open")}
                    </Link>{" "}
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={() => setConfirmDeleteId(c.id)}
                      disabled={busyDeleteId === c.id}
                    >
                      {busyDeleteId === c.id ? t("common.loading") : t("characters.actions.delete")}
                    </button>
                    {confirmDeleteId === c.id && (
                      <div style={{ marginTop: 8, padding: 8, background: "var(--surface-2)", borderRadius: 6 }}>
                        <p style={{ marginBottom: 8 }}><strong>{t("characters.deleteConfirmTitle")}</strong></p>
                        <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{t("characters.deleteConfirmBody")}</p>
                        <button type="button" className="btn btn-danger" onClick={() => handleDelete(c.id)}>
                          {t("common.delete")}
                        </button>{" "}
                        <button type="button" className="btn" onClick={() => setConfirmDeleteId(null)}>
                          {t("common.cancel")}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
            {total} total
          </div>
        </div>
      )}
    </div>
  );
}
