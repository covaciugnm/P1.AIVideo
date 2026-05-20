import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { AppFrame } from "@/components/AppFrame";
import { Providers } from "@/components/Providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "P1.AIVideo",
  description: "Controlled synthetic video generation platform",
  icons: {
    icon: "/AIVideo1.png",
    shortcut: "/AIVideo1.png",
    apple: "/AIVideo1.png",
  },
};

// Phase 22 — mobile viewport so the responsive CSS engages on phones.
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
          {/* AppFrame decides public (no shell) vs. authenticated (shell). */}
          <AppFrame>{children}</AppFrame>
        </Providers>
      </body>
    </html>
  );
}
