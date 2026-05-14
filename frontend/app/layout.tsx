import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { HeaderStatus } from "@/components/HeaderStatus";

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
        <div className="app-shell">
          <header className="app-header">
            <div className="app-header-left">
              <Link href="/" className="brand">
                P1.AIVideo
              </Link>
              <nav className="nav-links">
                <Link href="/">Dashboard</Link>
                <Link href="/jobs/new">New job</Link>
              </nav>
            </div>
            <HeaderStatus />
          </header>
          <main className="app-main">{children}</main>
          <footer className="app-footer">
            Synthetic-only pipeline. Every generated reel includes a mandatory
            AI-content disclosure. No real-person likeness or voice cloning.
          </footer>
        </div>
      </body>
    </html>
  );
}
