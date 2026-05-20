import type { Metadata, Viewport } from "next";
import dynamic from "next/dynamic";
import Link from "next/link";
import type { ReactNode } from "react";

import { BackendStatusBadge } from "@/components/BackendStatusBadge";
import { HelpButton } from "@/components/HelpButton";
import { HeaderRight, LocalizedFooter, LocalizedNav } from "@/components/LocalizedNav";
import { Providers } from "@/components/Providers";
import { RightSidebar } from "@/components/RightSidebar";

import "./globals.css";

// Help content (articles + search + renderer) is ~25 KB. Lazy-load it
// so the dashboard's first paint isn't bloated by docs nobody opened yet.
const HelpOverlay = dynamic(
  () => import("@/components/HelpOverlay").then((m) => m.HelpOverlay),
  { ssr: false }
);

export const metadata: Metadata = {
  title: "P1.AIVideo",
  description:
    "Synthetic-only short-form reel pipeline. Metadata-only operator dashboard.",
};

// Phase 22 — mobile viewport so the responsive CSS (globals.css media
// queries) actually engages on phones instead of rendering a zoomed-out
// desktop layout.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  readonly children: ReactNode;
}) {
  return (
    <html lang="ro">
      <body>
        <Providers>
          <div className="app-shell">
            <header className="app-header">
              <div className="app-header-left">
                <Link href="/" className="brand">
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
        </Providers>
      </body>
    </html>
  );
}
