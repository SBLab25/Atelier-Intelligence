import type { Metadata } from "next";
import { CockpitApp } from "@/cockpit/App";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = {
  title: "Analytics · CJI Atelier",
  description: "Customer Journey & Friction Telemetry Analytics.",
};

  export default async function AnalyticsPage() {
    const session = await requireSession();
    return (
      <CockpitApp
        initialViewMode="app"
        initialTab="analytics"
        session={{ label: session.label, role: session.role, journeys: session.journeys }}
      />
    );
  }
