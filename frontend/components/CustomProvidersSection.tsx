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

const CATEGORY_OPTIONS: readonly { value: ProviderCategory; label: string }[] = [
  { value: "llm", label: "LLM (scriptwriter)" },
  { value: "tts", label: "TTS (voice)" },
  { value: "video_generator", label: "Video generator" },
  { value: "audio_processor", label: "Audio processor" },
  { value: "image_processor", label: "Image processor" },
];

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
  void t("providers.addCustom");
  const [list, setList] = useState<CustomProviderInput[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [draft, setDraft] = useState<CustomProviderInput>(blankInput());
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

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
        <h3 className={styles.heading}>Custom providers</h3>
        <p className={styles.muted}>Loading…</p>
      </div>
    );
  }

  return (
    <div className={styles.section}>
      <div className={styles.headerRow}>
        <h3 className={styles.heading}>Custom providers</h3>
        <button
          type="button"
          className={styles.btn}
          onClick={() => {
            setShowForm((s) => !s);
            setError(null);
          }}
        >
          {showForm ? "Cancel" : "+ Add custom provider"}
        </button>
      </div>
      <p className={styles.note}>
        Metadata only. Adding a provider here registers it for job
        selection but does <strong>NOT</strong> install or configure the
        runtime. No shell execution, no package install, no backend file
        write. Secrets / API keys are not accepted.
      </p>

      {list.length === 0 && !showForm && (
        <p className={styles.muted}>No custom providers yet.</p>
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
                  aria-label={`Delete ${p.provider_id}`}
                >
                  ✕
                </button>
              </div>
              <div className={styles.flags}>
                {p.requires_gpu && <span className={styles.gpu}>GPU required</span>}
                {p.requires_network && <span className={styles.net}>requires network</span>}
                {p.requires_model_files && (
                  <span className={styles.assets}>requires model files</span>
                )}
                {!p.enabled && <span className={styles.disabled}>disabled</span>}
              </div>
              {p.notes && <p className={styles.notes}>{p.notes}</p>}
            </li>
          ))}
        </ul>
      )}

      {showForm && (
        <div className={styles.form}>
          <Field label="Category">
            <select
              className={styles.input}
              value={draft.category}
              onChange={(e) =>
                setDraft({ ...draft, category: e.target.value as ProviderCategory })
              }
            >
              {CATEGORY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="provider_id (slug-safe)">
            <input
              type="text"
              className={styles.input}
              value={draft.provider_id}
              onChange={(e) =>
                setDraft({ ...draft, provider_id: e.target.value.trim() })
              }
              placeholder="e.g. my_local_tts"
            />
          </Field>
          <Field label="Label">
            <input
              type="text"
              className={styles.input}
              value={draft.label}
              onChange={(e) => setDraft({ ...draft, label: e.target.value })}
            />
          </Field>
          <Field label="backend_type">
            <input
              type="text"
              className={styles.input}
              value={draft.backend_type}
              onChange={(e) => setDraft({ ...draft, backend_type: e.target.value })}
              placeholder="e.g. local_http"
            />
          </Field>
          <Field label="Local or external">
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
              <option value="local">local</option>
              <option value="external">external</option>
            </select>
          </Field>
          <Field label="Endpoint URL (optional, no credentials)">
            <input
              type="url"
              className={styles.input}
              value={draft.endpoint_url ?? ""}
              onChange={(e) => setDraft({ ...draft, endpoint_url: e.target.value })}
              placeholder="http://localhost:11434"
            />
          </Field>
          <Field label="Default model (optional)">
            <input
              type="text"
              className={styles.input}
              value={draft.default_model ?? ""}
              onChange={(e) => setDraft({ ...draft, default_model: e.target.value })}
            />
          </Field>
          <Field label="Supported models (comma-separated)">
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
              <span>requires network</span>
            </label>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={draft.requires_gpu}
                onChange={(e) =>
                  setDraft({ ...draft, requires_gpu: e.target.checked })
                }
              />
              <span>requires GPU</span>
            </label>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={draft.requires_model_files}
                onChange={(e) =>
                  setDraft({ ...draft, requires_model_files: e.target.checked })
                }
              />
              <span>requires model files</span>
            </label>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
              />
              <span>enabled</span>
            </label>
          </div>
          <Field label="Notes">
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
              Add
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
