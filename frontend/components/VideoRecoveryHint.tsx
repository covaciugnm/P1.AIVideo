"use client";

import Link from "next/link";

import { useT } from "@/lib/i18n/LanguageContext";

import styles from "./VideoRecoveryHint.module.css";

interface VideoRecoveryHintProps {
  readonly jobId: string;
  readonly rejectionReason: string | null | undefined;
  readonly canEdit: boolean;
  readonly canRetry: boolean;
}

/**
 * Phase 11E — when a job's rejection_reason matches a known video error
 * code (currently ``video_face_landmark_missing`` /
 * ``video_face_image_too_small``), surface a clean, localized
 * recovery card with Edit + Retry actions. The raw Python tail stays
 * available in the (rejection_reason / artifacts / timeline) blocks
 * for operators who want to dig.
 */
export function VideoRecoveryHint({
  jobId,
  rejectionReason,
  canEdit,
  canRetry,
}: VideoRecoveryHintProps) {
  const t = useT();
  if (!rejectionReason) return null;

  // The lipsync handler formats rejection_reason as
  // ``<error_code>: <operator message>`` so a simple prefix check is
  // enough. We also accept the legacy form where the code appears
  // anywhere in the string (older jobs from before Phase 11E).
  const matchCode = (code: string): boolean =>
    rejectionReason.startsWith(`${code}:`) || rejectionReason.includes(code);

  let titleKey: string | null = null;
  let bodyKey: string | null = null;
  if (matchCode("video_face_landmark_missing")) {
    titleKey = "videoRecovery.faceLandmarkMissingTitle";
    bodyKey = "videoRecovery.faceLandmarkMissingBody";
  } else if (matchCode("video_face_image_too_small")) {
    titleKey = "videoRecovery.faceImageTooSmallTitle";
    bodyKey = "videoRecovery.faceImageTooSmallBody";
  }
  if (!titleKey || !bodyKey) return null;

  return (
    <section className={`card ${styles.recovery}`}>
      <h2 className={styles.title}>{t(titleKey)}</h2>
      <p className={styles.body}>{t(bodyKey)}</p>
      <p className={styles.muted}>
        {t("videoRecovery.portraitRequirements")}
      </p>
      <div className={styles.actions}>
        {canEdit && (
          <Link
            href={`/jobs/${jobId}/edit`}
            className="btn btn-primary"
            aria-label={t("videoRecovery.editAndReplaceImage")}
          >
            {t("videoRecovery.editAndReplaceImage")}
          </Link>
        )}
        {canRetry && (
          <span className={styles.retryNote}>
            {t("videoRecovery.retryAfterEdit")}
          </span>
        )}
      </div>
    </section>
  );
}
