"use client";

import Link from "next/link";

import { HelpLink } from "@/components/HelpHint";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useT } from "@/lib/i18n/LanguageContext";

export function LocalizedNav() {
  const t = useT();
  return (
    <nav className="nav-links">
      <Link href="/">{t("nav.dashboard")}</Link>
      <Link href="/jobs">{t("nav.jobs")}</Link>
      <Link href="/jobs/new">{t("nav.newJob")}</Link>
      <Link href="/uploads">{t("nav.uploads")}</Link>
      <Link href="/settings">{t("nav.settings")}</Link>
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
