"use client";

import { useEffect, useState } from "react";

import { useT } from "@/lib/i18n/LanguageContext";
import * as logBus from "@/lib/log-bus";
import {
  type CustomProviderInput,
  loadCustomProviders,
  saveCustomProviders,
  validateCustomProvider,
} from "@/lib/customProviders";
import type { ProviderCategory, ProviderLocality } from "@/lib/types";

import styles from "./CustomProvidersSection.module.css";

function blankInput(): CustomProviderInput {
  return {
    category: "llm",
    provider_id: "",
    label: "",
    backend_type: "local_http",
    local_or_external: "local",
    endpoint_url: "",
    default_model: "",
    supported_models: [],
    requires_network: false,
    requires_gpu: false,
    requires_model_files: false,
    enabled: true,
    notes: "",
  };
}

export function CustomProvidersSection() {
  const t = useT();
  const [list, setList] = useState<CustomProviderInput[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [draft, setDraft] = useState<CustomProviderInput>(blankInput());
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const categoryOptions: readonly { value: ProviderCategory; label: string }[] = [
    { value: "llm", label: t("providers.categoryLlm") },
    { value: "tts", label: t("providers.categoryTts") },
    { value: "video_generator", label: t("providers.categoryVideo") },
    { value: "audio_processor", label: t("providers.categoryAudioProcessor") },
    { value: "image_processor", label: t("providers.categoryImageProcessor") },
  ];

  useEffect(() => {
    setList(loadCustomProviders());
    setHydrated(true);
  }, []);

  const persist = (next: CustomProviderInput[]) => {
    setList(next);
    saveCustomProviders(next);
  };

  const handleAdd = () => {
    const err = validateCustomProvider(draft);
    if (err) {
      setError(err);
      return;
    }
    const existing = list.find(
      (p) => p.category === draft.category && p.provider_id === draft.provider_id,
    );
    if (existing) {
      // Phase 11A — window.confirm remains untranslated in the prompt
      // but we could use a custom Modal later. For now we use standard
      // confirm which is browser-localized.
      if (
        !window.confirm(
          `Overwrite existing custom provider "${draft.provider_id}" in category "${draft.category}"?`,
        )
      ) {
        return;
      }
    }
    const next = list.filter(
      (p) => !(p.category === draft.category && p.provider_id === draft.provider_id),
    );
    next.push({
      ...draft,
      supported_models: (draft.supported_models ?? []).filter((s) => s.trim()),
    });
    persist(next);
    setError(null);
    setDraft(blankInput());
    setShowForm(false);
    logBus.emit({
      source: "frontend",
      level: "info",
      message: `custom provider added: ${draft.category}/${draft.provider_id}`,
      meta: {
        category: draft.category,
        provider_id: draft.provider_id,
        is_custom: true,
      },
    });
  };

  const handleDelete = (p: CustomProviderInput) => {
    if (
      !window.confirm(
        `Remove custom provider "${p.provider_id}" from category "${p.category}"?`,
      )
    ) {
      return;
    }
    persist(
      list.filter(
        (q) => !(q.category === p.category && q.provider_id === p.provider_id),
      ),
    );
    logBus.emit({
      source: "frontend",
      level: "info",
      message: `custom provider deleted: ${p.category}/${p.provider_id}`,
      meta: { category: p.category, provider_id: p.provider_id },
    });
  };

  if (!hydrated) {
    return (
      <div className={styles.section}>
        <h3 className={styles.heading}>{t("customProviders.title")}</h3>
        <p className={styles.muted}>{t("customProviders.loading")}</p>
      </div>
    );
  }

  return (
    <div className={styles.section}>
      <div className={styles.headerRow}>
        <h3 className={styles.heading}>{t("customProviders.title")}</h3>
        <button
          type="button"
          className={styles.btn}
          onClick={() => {
            setShowForm((s) => !s);
            setError(null);
          }}
        >
          {showForm ? t("customProviders.cancel") : t("customProviders.add")}
        </button>
      </div>
      <p className={styles.note}>{t("customProviders.metadataOnlyNote")}</p>

      {list.length === 0 && !showForm && (
        <p className={styles.muted}>{t("customProviders.noCustom")}</p>
      )}

      {list.length > 0 && (
        <ul className={styles.list}>
          {list.map((p) => (
            <li key={`${p.category}-${p.provider_id}`} className={styles.item}>
              <div className={styles.itemRow}>
                <span className={styles.category}>{p.category}</span>
                <code className={styles.providerId}>{p.provider_id}</code>
                <span className={styles.itemLabel}>{p.label}</span>
                <span className={styles.locality}>{p.local_or_external}</span>
                <button
                  type="button"
                  className={styles.delete}
                  onClick={() => handleDelete(p)}
                  aria-label={t("customProviders.deleteAria", { id: p.provider_id })}
                >
                  ✕
                </button>
              </div>
              <div className={styles.flags}>
                {p.requires_gpu && <span className={styles.gpu}>{t("customProviders.gpuRequiredFlag")}</span>}
                {p.requires_network && <span className={styles.net}>{t("customProviders.requiresNetwork")}</span>}
                {p.requires_model_files && (
                  <span className={styles.assets}>{t("customProviders.requiresModelFiles")}</span>
                )}
                {!p.enabled && <span className={styles.disabled}>{t("customProviders.disabled")}</span>}
              </div>
              {p.notes && <p className={styles.notes}>{p.notes}</p>}
            </li>
          ))}
        </ul>
      )}

      {showForm && (
        <div className={styles.form}>
          <Field label={t("customProviders.category")}>
            <select
              className={styles.input}
              value={draft.category}
              onChange={(e) =>
                setDraft({ ...draft, category: e.target.value as ProviderCategory })
              }
            >
              {categoryOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("customProviders.providerIdSlugSafe")}>
            <input
              type="text"
              className={styles.input}
              value={draft.provider_id}
              onChange={(e) =>
                setDraft({ ...draft, provider_id: e.target.value.trim() })
              }
              placeholder={t("customProviders.providerIdPlaceholder")}
            />
          </Field>
          <Field label={t("customProviders.label")}>
            <input
              type="text"
              className={styles.input}
              value={draft.label}
              onChange={(e) => setDraft({ ...draft, label: e.target.value })}
            />
          </Field>
          <Field label={t("customProviders.backendType")}>
            <input
              type="text"
              className={styles.input}
              value={draft.backend_type}
              onChange={(e) => setDraft({ ...draft, backend_type: e.target.value })}
              placeholder={t("customProviders.backendTypePlaceholder")}
            />
          </Field>
          <Field label={t("customProviders.localityField")}>
            <select
              className={styles.input}
              value={draft.local_or_external}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  local_or_external: e.target.value as ProviderLocality,
                })
              }
            >
              <option value="local">{t("customProviders.localityLocal")}</option>
              <option value="external">{t("customProviders.localityExternal")}</option>
            </select>
          </Field>
          <Field label={t("customProviders.endpointUrlOptional")}>
            <input
              type="url"
              className={styles.input}
              value={draft.endpoint_url ?? ""}
              onChange={(e) => setDraft({ ...draft, endpoint_url: e.target.value })}
              placeholder={t("customProviders.endpointUrlPlaceholder")}
            />
          </Field>
          <Field label={t("customProviders.defaultModelOptional")}>
            <input
              type="text"
              className={styles.input}
              value={draft.default_model ?? ""}
              onChange={(e) => setDraft({ ...draft, default_model: e.target.value })}
            />
          </Field>
          <Field label={t("customProviders.supportedModelsCsv")}>
            <input
              type="text"
              className={styles.input}
              value={(draft.supported_models ?? []).join(", ")}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  supported_models: e.target.value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
            />
          </Field>
          <div className={styles.checkRow}>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={draft.requires_network}
                onChange={(e) =>
                  setDraft({ ...draft, requires_network: e.target.checked })
                }
              />
              <span>{t("customProviders.requiresNetwork")}</span>
            </label>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={draft.requires_gpu}
                onChange={(e) =>
                  setDraft({ ...draft, requires_gpu: e.target.checked })
                }
              />
              <span>{t("customProviders.requiresGpu")}</span>
            </label>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={draft.requires_model_files}
                onChange={(e) =>
                  setDraft({ ...draft, requires_model_files: e.target.checked })
                }
              />
              <span>{t("customProviders.requiresModelFiles")}</span>
            </label>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
              />
              <span>{t("customProviders.enabled")}</span>
            </label>
          </div>
          <Field label={t("customProviders.notes")}>
            <input
              type="text"
              className={styles.input}
              value={draft.notes ?? ""}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            />
          </Field>
          {error && <p className={styles.err}>{error}</p>}
          <div className={styles.formActions}>
            <button type="button" className={styles.btnPrimary} onClick={handleAdd}>
              {t("customProviders.addAction")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  children,
}: {
  readonly label: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div className={styles.field}>
      <label className={styles.fieldLabel}>{label}</label>
      {children}
    </div>
  );
}
