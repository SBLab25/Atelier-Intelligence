import type { Metadata } from "next";
import { CockpitApp } from "@/cockpit/App";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = {
  title: "Team & Operations · CJI Atelier",
  description: "Human resources, capacity allocation, and velocity.",
};

  export default async function TeamPage() {
    const session = await requireSession();
    return (
      <CockpitApp
        initialViewMode="app"
        initialTab="team"
        session={{ label: session.label, role: session.role, journeys: session.journeys }}
      />
    );
  }
