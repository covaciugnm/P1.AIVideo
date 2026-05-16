import type { Metadata } from "next";
import dynamic from "next/dynamic";
import Link from "next/link";
import type { ReactNode } from "react";

import { BackendStatusBadge } from "@/components/BackendStatusBadge";
import { HelpButton } from "@/components/HelpButton";
import { HelpLink } from "@/components/HelpHint";
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

export default function RootLayout({
  children,
}: {
  readonly children: ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <div className="app-shell">
            <header className="app-header">
              <div className="app-header-left">
                <Link href="/" className="brand">
                  P1.AIVideo
                </Link>
                <nav className="nav-links">
                  <Link href="/">Dashboard</Link>
                  <Link href="/jobs">Jobs</Link>
                  <Link href="/jobs/new">New job</Link>
                  <Link href="/uploads">Uploads</Link>
                  <Link href="/settings">Settings</Link>
                  <HelpLink>Help</HelpLink>
                </nav>
              </div>
              <BackendStatusBadge />
            </header>
            <div className="app-body">
              <main className="app-main">
                <div className="content-wrapper">{children}</div>
              </main>
              <RightSidebar />
            </div>
            <footer className="app-footer">
              Synthetic-only pipeline. Every generated reel includes a mandatory
              AI-content disclosure. No real-person likeness or voice cloning.
              <span style={{ marginLeft: 12 }}>
                <HelpLink>Need help? Open the help center →</HelpLink>
              </span>
            </footer>
            <HelpButton />
            <HelpOverlay />
          </div>
        </Providers>
      </body>
    </html>
  );
}
