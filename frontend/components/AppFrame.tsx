"use client";

// AppFrame — the single decider for public vs. private rendering.
//
// Public routes (/, /login, /register) render ONLY their page content with
// no internal shell. Protected routes render the internal app shell
// (header/nav/right sidebar/footer/help) ONLY after a token is confirmed;
// otherwise they redirect to /login and never paint the shell.

import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { BackendStatusBadge } from "@/components/BackendStatusBadge";
import { HelpButton } from "@/components/HelpButton";
import { HeaderRight, LocalizedFooter, LocalizedNav } from "@/components/LocalizedNav";
import { RightSidebar } from "@/components/RightSidebar";
import { getToken } from "@/lib/auth";

const HelpOverlay = dynamic(
  () => import("@/components/HelpOverlay").then((m) => m.HelpOverlay),
  { ssr: false },
);

const PUBLIC_PATHS = ["/", "/login", "/register"];

function isPublicPath(pathname: string | null): boolean {
  if (!pathname) return true;
  return PUBLIC_PATHS.some((p) => (p === "/" ? pathname === "/" : pathname.startsWith(p)));
}

function Splash({ label }: { readonly label: string }) {
  return (
    <div className="auth-splash">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/AIVideo1.png" alt="P1.AIVideo" style={{ height: 56, marginBottom: 16 }} />
      <p className="muted">{label}</p>
    </div>
  );
}

export function AppFrame({ children }: { readonly children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const publicRoute = isPublicPath(pathname);
  const [authState, setAuthState] = useState<"checking" | "authed" | "noauth">("checking");

  useEffect(() => {
    if (publicRoute) return;
    const token = getToken();
    if (!token) {
      setAuthState("noauth");
      router.replace("/login");
      return;
    }
    setAuthState("authed");
  }, [publicRoute, pathname, router]);

  // Public pages: NO internal shell at all.
  if (publicRoute) {
    return <main className="public-main">{children}</main>;
  }

  // Protected pages: never render the shell until auth is confirmed.
  if (authState !== "authed") {
    return <Splash label={authState === "noauth" ? "Redirecting to sign in…" : "Checking access…"} />;
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-left">
          <Link href="/characters" className="brand">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/AIVideo1.png" alt="" style={{ height: 22, verticalAlign: "middle", marginRight: 8 }} />
            P1.AIVideo
          </Link>
          <LocalizedNav />
        </div>
        <div style={{ display: "inline-flex", gap: 12, alignItems: "center" }}>
          <HeaderRight />
          <BackendStatusBadge />
        </div>
      </header>
      <div className="app-body">
        <main className="app-main">
          <div className="content-wrapper">{children}</div>
        </main>
        <RightSidebar />
      </div>
      <footer className="app-footer">
        <LocalizedFooter />
      </footer>
      <HelpButton />
      <HelpOverlay />
    </div>
  );
}
