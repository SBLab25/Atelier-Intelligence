import type { Metadata } from "next";
import { CockpitApp } from "@/cockpit/App";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = {
  title: "Dashboard · CJI Atelier",
  description: "Tactile Bento Modular System Overview & Velocity Telemetry.",
};

  export default async function DashboardPage() {
    const session = await requireSession();
    return (
      <CockpitApp
        initialViewMode="app"
        initialTab="dashboard"
        session={{ label: session.label, role: session.role, journeys: session.journeys }}
      />
    );
  }
