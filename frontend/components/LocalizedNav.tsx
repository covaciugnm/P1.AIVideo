"use client";

import Link from "next/link";

import { HelpLink } from "@/components/HelpHint";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useT } from "@/lib/i18n/LanguageContext";

export function LocalizedNav() {
  const t = useT();
  return (
    <nav className="nav-links">
      {/* Phase 21 user iteration:
          - Dashboard tab removed (it duplicated the videos list).
          - Personaje (Characters) reordered to come BEFORE Video-uri
            so the operator picks the persona FIRST, then generates
            videos for it.
          - "Adaugă video" button stays only on the Videos page
            (top-right) — never in the global nav. */}
      <Link href="/characters">{t("nav.characters")}</Link>
      <Link href="/jobs">{t("nav.jobs")}</Link>
      <Link href="/uploads">{t("nav.uploads")}</Link>
      <Link href="/settings">{t("nav.settings")}</Link>
      <Link href="/technical-help" data-testid="nav-technical">{t("nav.technical")}</Link>
      <HelpLink>{t("nav.help")}</HelpLink>
    </nav>
  );
}

export function LocalizedFooter() {
  const t = useT();
  return (
    <>
      <span>{t("footer.complianceLine")}</span>
      <span style={{ marginLeft: 12 }}>
        <HelpLink>{t("footer.helpLink")}</HelpLink>
      </span>
    </>
  );
}

export function HeaderRight() {
  return (
    <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
      <LanguageSwitcher compact />
    </span>
  );
}
