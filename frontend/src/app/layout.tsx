import "@fontsource/plus-jakarta-sans/400.css";
import "@fontsource/plus-jakarta-sans/500.css";
import "@fontsource/plus-jakarta-sans/600.css";
import "@fontsource/plus-jakarta-sans/700.css";
import "@fontsource/space-grotesk/400.css";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/600.css";
import "material-symbols/outlined.css";
import "./atelier.css";
import "./globals.css";

import type { Metadata } from "next";
import type { ReactNode } from "react";

// Every page is rendered per request: pages depend on the session, and the CSP nonce is per request (OD-136).
// Without this, pages without dynamic inputs would be prerendered at build time (with no session).
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "CJI",
  description: "Customer Journey Intelligence",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { readonly children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}
