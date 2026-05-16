"use client";

import { useEffect, useState } from "react";

import { generateTts, getProviders } from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageContext";
import * as logBus from "@/lib/log-bus";
import type { ProviderInfo, ProvidersResponse } from "@/lib/types";

import styles from "./ProvidersSection.module.css";

interface ProvidersSectionProps {
  readonly defaults: {
    readonly llm: string | null;
    readonly tts: string | null;
    readonly video: string | null;
  };
  readonly onDefaultsChange: (patch: {
    readonly llm?: string | null;
    readonly tts?: string | null;
    readonly video?: string | null;
  }) => void;
}

export function ProvidersSection({
  defaults,
  onDefaultsChange,
}: ProvidersSectionProps) {
  const t = useT();
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ttsTest, setTtsTest] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const p = await getProviders(controller.signal);
        setProviders(p);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => controller.abort();
  }, []);

  const handleTestTts = async (providerId: string) => {
    setTtsTest(t("providersSection.ttsTestRunning"));
    const res = await generateTts({
      script_text: "Test sample for provider preview.",
      tts_provider_id: providerId,
    });
    if (!res.ok) {
      setTtsTest(t("providersSection.ttsTestFailure", { error: res.error.code }));
      logBus.emit({
        source: "frontend",
        level: res.httpStatus === 503 ? "warning" : "error",
        message: `tts test ${providerId} → ${res.error.code}`,
        meta: { providerId, code: res.error.code, status: res.httpStatus },
      });
    } else {
      setTtsTest(t("providersSection.ttsTestSuccess"));
    }
  };

  if (error) {
    return (
      <div className={styles.section}>
        <h3 className={styles.heading}>{t("providers.providersTitle")}</h3>
        <p className={styles.err}>{t("providers.failedToLoad", { detail: error })}</p>
      </div>
    );
  }
  if (!providers) {
    return (
      <div className={styles.section}>
        <h3 className={styles.heading}>{t("providers.providersTitle")}</h3>
        <p className={styles.muted}>{t("providers.loadingProviders")}</p>
      </div>
    );
  }

  return (
    <div className={styles.section}>
      <h3 className={styles.heading}>{t("providers.providersTitle")}</h3>

      <Category
        title={t("providers.categoryLlm")}
        providers={providers.llm}
        defaultValue={defaults.llm}
        onChange={(v) => onDefaultsChange({ llm: v })}
        testButton={null}
      />

      <Category
        title={t("providers.categoryTts")}
        providers={providers.tts}
        defaultValue={defaults.tts}
        onChange={(v) => onDefaultsChange({ tts: v })}
        testButton={(p) => (
          <button
            type="button"
            className={styles.btnSmall}
            onClick={() => handleTestTts(p.provider_id)}
          >
            {t("common.test")}
          </button>
        )}
      />
      {ttsTest && <p className={styles.testNote}>{ttsTest}</p>}

      <Category
        title={t("providers.categoryVideo")}
        providers={providers.video_generator}
        defaultValue={defaults.video}
        onChange={(v) => onDefaultsChange({ video: v })}
        testButton={null}
      />

      <p className={styles.muted}>
        {t("providers.addingProviderNote")}
      </p>
    </div>
  );
}

interface CategoryProps {
  readonly title: string;
  readonly providers: readonly ProviderInfo[];
  readonly defaultValue: string | null;
  readonly onChange: (v: string | null) => void;
  readonly testButton: ((p: ProviderInfo) => React.ReactNode) | null;
}

function Category({
  title,
  providers,
  defaultValue,
  onChange,
  testButton,
}: CategoryProps) {
  const t = useT();
  return (
    <div className={styles.category}>
      <div className={styles.categoryHeader}>
        <span className={styles.categoryTitle}>{title}</span>
        <select
          className={styles.select}
          value={defaultValue ?? ""}
          onChange={(e) => onChange(e.target.value || null)}
        >
          <option value="">{t("providers.defaultOption")}</option>
          {providers.map((p) => (
            <option key={p.provider_id} value={p.provider_id}>
              {p.label}
            </option>
          ))}
        </select>
      </div>
      <ul className={styles.list}>
        {providers.map((p) => (
          <li key={p.provider_id} className={styles.item}>
            <div className={styles.itemRow}>
              <code className={styles.providerId}>{p.provider_id}</code>
              <span
                className={`${styles.status} ${styles[`status-${p.status}`] ?? ""}`}
              >
                {t(`providerStatuses.${p.status}` as any)}
              </span>
              <span className={styles.modelLabel}>
                {p.default_model ?? "—"}
              </span>
              <span className={styles.locality}>
                {p.is_local ? t("providers.isLocal").toLowerCase() : "external"}
              </span>
              {testButton && testButton(p)}
            </div>
            {p.notes && <p className={styles.notes}>{p.notes}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
