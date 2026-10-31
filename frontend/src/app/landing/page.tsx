import type { Metadata } from "next";
import { LandingClient } from "./LandingClient";

export const metadata: Metadata = {
  title: "Atelier Intelligence · Customer Journey Intelligence",
  description: "Tactile Bento Modular System for Quantitative Customer Journey Analytics.",
};

export default function Page() {
  return (
    <main id="main" className="min-h-screen bg-background">
      <LandingClient />
    </main>
  );
}

