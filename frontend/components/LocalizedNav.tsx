"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { HelpLink } from "@/components/HelpHint";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useT } from "@/lib/i18n/LanguageContext";
import { getCurrentUser, getToken, isProtectedSuperAdmin, logout, type CurrentUser } from "@/lib/auth";

const PUBLIC_PATHS = ["/login", "/register"];

/** Client-side auth gate: bounce to /login when no token (except public pages). */
function useAuthGate(): CurrentUser | null {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<CurrentUser | null>(null);
  useEffect(() => {
    const isPublic = PUBLIC_PATHS.some((p) => pathname?.startsWith(p));
    const token = getToken();
    if (!token && !isPublic) {
      router.replace("/login");
      return;
    }
    setUser(getCurrentUser());
  }, [pathname, router]);
  return user;
}

export function LocalizedNav() {
  const t = useT();
  const user = useAuthGate();
  const showUsers = isProtectedSuperAdmin(user);
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
      {showUsers && <Link href="/users" data-testid="nav-users">Users</Link>}
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
  const [user, setUser] = useState<CurrentUser | null>(null);
  useEffect(() => { setUser(getCurrentUser()); }, []);
  return (
    <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
      <LanguageSwitcher compact />
      {user && (
        <>
          <span className="muted" data-testid="current-username" style={{ fontSize: 12 }}>
            {user.username}
          </span>
          <button type="button" className="btn" data-testid="logout-btn" onClick={() => logout()}>
            Logout
          </button>
        </>
      )}
    </span>
  );
}
