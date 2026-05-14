import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { BackendStatusBadge } from "@/components/BackendStatusBadge";
import { Providers } from "@/components/Providers";
import { RightSidebar } from "@/components/RightSidebar";

import "./globals.css";

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
            </footer>
          </div>
        </Providers>
      </body>
    </html>
  );
}
