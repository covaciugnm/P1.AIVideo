"use client";

// Phase 12X — DB-backed API key store displayed in the right-sidebar
// "Keys" tab. Keys are persisted in the ``api_secrets`` table; on
// backend startup every row is pushed into ``os.environ`` so adapters
// pick them up across Docker restarts. Per the operator's explicit
// request, values are shown in clear text (no masking).

import { useEffect, useMemo, useState } from "react";

import {
  type ApiSecret,
  type ApiSecretCatalogEntry,
  type ApiSecretTestResponse,
  deleteSecret,
  listSecrets,
  saveSecret,
  testSecret,
} from "@/lib/secrets";
import { useT } from "@/lib/i18n/LanguageContext";
import * as logBus from "@/lib/log-bus";

import styles from "./KeysPanel.module.css";

interface RowState {
  readonly value: string;
  readonly busy: boolean;
  readonly testResult: ApiSecretTestResponse | null;
}

export function KeysPanel() {
  const t = useT();
  const [secrets, setSecrets] = useState<readonly ApiSecret[]>([]);
  const [catalog, setCatalog] = useState<readonly ApiSecretCatalogEntry[]>([]);
  const [drafts, setDrafts] = useState<Record<string, RowState>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await listSecrets();
      setSecrets(r.items);
      setCatalog(r.catalog);
      setDrafts((prev) => {
        const next: Record<string, RowState> = {};
        for (const cat of r.catalog) {
          const persisted = r.items.find((s) => s.key_name === cat.key_name);
          next[cat.key_name] = {
            value: persisted?.value ?? prev[cat.key_name]?.value ?? "",
            busy: false,
            testResult: null,
          };
        }
        // Add ad-hoc keys (persisted but not in catalog).
        for (const s of r.items) {
          if (!next[s.key_name]) {
            next[s.key_name] = {
              value: s.value,
              busy: false,
              testResult: null,
            };
          }
        }
        return next;
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
  }, []);

  const rows = useMemo(() => {
    const cat = [...catalog];
    const extras = secrets.filter(
      (s) => !catalog.some((c) => c.key_name === s.key_name),
    );
    return [
      ...cat,
      ...extras.map((s) => ({
        key_name: s.key_name,
        description: s.description ?? "(custom key)",
        category: s.category,
        test_probe: "operator-defined",
      })),
    ];
  }, [catalog, secrets]);

  const handleSave = async (key_name: string) => {
    const row = drafts[key_name];
    if (!row) return;
    setDrafts((p) => ({ ...p, [key_name]: { ...p[key_name], busy: true } }));
    // Only the key_name (identifier) is logged — never the secret value.
    logBus.emit({ source: "frontend", level: "info", message: "key upsert submitted", meta: { key_name } });
    try {
      await saveSecret(
        key_name,
        row.value,
        catalog.find((c) => c.key_name === key_name)?.description ?? null,
        catalog.find((c) => c.key_name === key_name)?.category ?? "misc",
      );
      await reload();
      logBus.emit({ source: "frontend", level: "success", message: `key upsert → ${key_name}`, meta: { key_name } });
    } catch (err) {
      const msg = (err as Error).message;
      setError(msg);
      logBus.emit({ source: "frontend", level: "error", message: "key upsert failed", meta: { key_name, error: msg } });
    } finally {
      setDrafts((p) => ({ ...p, [key_name]: { ...p[key_name], busy: false } }));
    }
  };

  const handleTest = async (key_name: string) => {
    setDrafts((p) => ({ ...p, [key_name]: { ...p[key_name], busy: true } }));
    logBus.emit({ source: "frontend", level: "info", message: "key test submitted", meta: { key_name } });
    try {
      const r = await testSecret(key_name);
      setDrafts((p) => ({
        ...p,
        [key_name]: { ...p[key_name], testResult: r, busy: false },
      }));
      logBus.emit({
        source: "frontend",
        level: r.status === "ok" ? "success" : "warning",
        message: `key test ${key_name} → ${r.status}`,
        meta: { key_name, status: r.status },
      });
    } catch (err) {
      const msg = (err as Error).message;
      setError(msg);
      setDrafts((p) => ({ ...p, [key_name]: { ...p[key_name], busy: false } }));
      logBus.emit({ source: "frontend", level: "error", message: "key test failed", meta: { key_name, error: msg } });
    }
  };

  const handleDelete = async (key_name: string) => {
    if (!confirm(t("keys.confirmDelete", { name: key_name }))) return;
    logBus.emit({ source: "frontend", level: "info", message: "key delete submitted", meta: { key_name } });
    try {
      await deleteSecret(key_name);
      await reload();
      logBus.emit({ source: "frontend", level: "success", message: `key delete → ${key_name}`, meta: { key_name } });
    } catch (err) {
      const msg = (err as Error).message;
      setError(msg);
      logBus.emit({ source: "frontend", level: "error", message: "key delete failed", meta: { key_name, error: msg } });
    }
  };

  const groups = useMemo(() => {
    const order: { id: string; label: string }[] = [
      { id: "huggingface", label: t("keys.categories.huggingface") },
      { id: "image_generator", label: t("keys.categories.image_generator") },
      { id: "llm", label: t("keys.categories.llm") },
      { id: "tts", label: t("keys.categories.tts") },
      { id: "local_endpoint", label: t("keys.categories.local_endpoint") },
      { id: "misc", label: t("keys.categories.misc") },
    ];
    return order.map((g) => ({
      ...g,
      rows: rows.filter((r) => r.category === g.id),
    }));
  }, [rows, t]);

  return (
    <div className={styles.panel}>
      <header className={styles.header}>
        <h3>{t("keys.title")}</h3>
        <p className={styles.intro}>{t("keys.intro")}</p>
      </header>
      {error && <p className={styles.error}>{error}</p>}
      {loading && <p>{t("common.loading")}</p>}
      {!loading &&
        groups.map((g) => {
          if (g.rows.length === 0) return null;
          return (
            <section key={g.id} className={styles.section}>
              <h4>{g.label}</h4>
              {g.rows.map((entry) => {
                const draft = drafts[entry.key_name] ?? {
                  value: "",
                  busy: false,
                  testResult: null,
                };
                const persisted = secrets.find(
                  (s) => s.key_name === entry.key_name,
                );
                const statusBadge = (() => {
                  const status =
                    draft.testResult?.status ?? persisted?.last_test_status;
                  if (status === "ok") return <span className={styles.ok}>● OK</span>;
                  if (status === "failed")
                    return <span className={styles.bad}>● FAIL</span>;
                  if (status === "skipped")
                    return <span className={styles.muted}>● —</span>;
                  return <span className={styles.muted}>● ?</span>;
                })();
                return (
                  <div key={entry.key_name} className={styles.row}>
                    <div className={styles.rowHead}>
                      <code className={styles.keyName}>{entry.key_name}</code>
                      {statusBadge}
                    </div>
                    <div className={styles.desc}>{entry.description}</div>
                    <div className={styles.controls}>
                      <input
                        type="text"
                        value={draft.value}
                        placeholder={t("keys.placeholder")}
                        onChange={(e) =>
                          setDrafts((p) => ({
                            ...p,
                            [entry.key_name]: {
                              ...p[entry.key_name],
                              value: e.target.value,
                            },
                          }))
                        }
                        className={styles.input}
                      />
                      <button
                        type="button"
                        onClick={() => handleSave(entry.key_name)}
                        disabled={draft.busy}
                        className={styles.btnSave}
                      >
                        {t("keys.save")}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleTest(entry.key_name)}
                        disabled={draft.busy || !draft.value}
                        className={styles.btnTest}
                      >
                        {t("keys.test")}
                      </button>
                      {persisted && (
                        <button
                          type="button"
                          onClick={() => handleDelete(entry.key_name)}
                          className={styles.btnDelete}
                        >
                          {t("common.delete")}
                        </button>
                      )}
                    </div>
                    {(draft.testResult || persisted?.last_test_detail) && (
                      <div className={styles.detail}>
                        {draft.testResult?.detail ?? persisted?.last_test_detail}
                      </div>
                    )}
                    <div className={styles.probe}>
                      <em>{t("keys.probe")}:</em> {entry.test_probe}
                    </div>
                  </div>
                );
              })}
            </section>
          );
        })}
    </div>
  );
}
