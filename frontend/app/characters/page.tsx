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
  type DeleteImpact,
  deleteCharacter,
  getDeleteImpact,
  listCharacters,
} from "@/lib/characters";
import { useT } from "@/lib/i18n/LanguageContext";
import * as logBus from "@/lib/log-bus";

export default function CharactersPage() {
  const t = useT();
  const [items, setItems] = useState<readonly CharacterSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [busyDeleteId, setBusyDeleteId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  // Two-step destructive confirm: stage 1 shows impact, stage 2 final confirm.
  const [deleteStage, setDeleteStage] = useState(0);
  const [impact, setImpact] = useState<DeleteImpact | null>(null);

  const startDelete = async (id: string) => {
    setConfirmDeleteId(id);
    setDeleteStage(1);
    setImpact(null);
    try {
      setImpact(await getDeleteImpact(id));
    } catch {
      setImpact({ character: "", images: 0, videos: 0, jobs: 0 });
    }
  };

  const cancelDelete = () => {
    setConfirmDeleteId(null);
    setDeleteStage(0);
    setImpact(null);
  };

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
    logBus.emit({ source: "frontend", level: "info", message: "character delete submitted", meta: { character_id: id } });
    try {
      await deleteCharacter(id, { hard: true }); // purge identity + images + videos + jobs
      await reload();
      logBus.emit({ source: "frontend", level: "success", message: `character delete → ${id}`, meta: { character_id: id } });
    } catch (err) {
      const e = err as Error;
      setError(e);
      logBus.emit({ source: "frontend", level: "error", message: "character delete failed", meta: { character_id: id, error: e.message } });
    } finally {
      setBusyDeleteId(null);
      cancelDelete();
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
                      onClick={() => startDelete(c.id)}
                      disabled={busyDeleteId === c.id}
                    >
                      {busyDeleteId === c.id ? t("common.loading") : t("characters.actions.delete")}
                    </button>
                    {confirmDeleteId === c.id && (
                      <div style={{ marginTop: 8, padding: 12, background: "var(--surface-2)", borderRadius: 6, border: "1px solid var(--danger)", maxWidth: 360, whiteSpace: "normal" }}>
                        <p style={{ margin: "0 0 6px", fontWeight: 700, color: "var(--danger)" }}>
                          ⚠ Ștergere definitivă — {c.display_name || c.name}
                        </p>
                        <p className="muted" style={{ fontSize: 12, margin: "0 0 8px" }}>
                          Aceasta șterge IREVERSIBIL tot ce ține de personaj:
                        </p>
                        <ul className="muted" style={{ fontSize: 12, margin: "0 0 10px", paddingLeft: 18 }}>
                          <li>Profilul de identitate</li>
                          <li>{impact ? impact.images : "…"} imagini (inclusiv fișierele)</li>
                          <li>{impact ? impact.videos : "…"} videoclipuri</li>
                          <li>{impact ? impact.jobs : "…"} joburi asociate</li>
                        </ul>
                        {deleteStage === 1 ? (
                          <>
                            <button type="button" className="btn btn-danger" onClick={() => setDeleteStage(2)}>
                              Continuă (1/2)
                            </button>{" "}
                            <button type="button" className="btn" onClick={cancelDelete}>
                              {t("common.cancel")}
                            </button>
                          </>
                        ) : (
                          <>
                            <p style={{ fontSize: 12, fontWeight: 700, margin: "0 0 8px" }}>
                              Ești absolut sigur? Acțiunea nu poate fi anulată.
                            </p>
                            <button type="button" className="btn btn-danger" onClick={() => handleDelete(c.id)} disabled={busyDeleteId === c.id}>
                              {busyDeleteId === c.id ? t("common.loading") : "Șterge definitiv tot (2/2)"}
                            </button>{" "}
                            <button type="button" className="btn" onClick={cancelDelete}>
                              {t("common.cancel")}
                            </button>
                          </>
                        )}
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
