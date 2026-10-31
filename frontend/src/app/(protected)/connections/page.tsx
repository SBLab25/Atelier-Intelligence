import type { Metadata } from "next";
import { CockpitApp } from "@/cockpit/App";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = {
  title: "Connections · CJI Atelier",
  description: "Client Side Integration Hub, Tracking Snippets & Multi-Site Connectors.",
};

export default async function ConnectionsPage() {
  const session = await requireSession();
  return (
    <CockpitApp
      initialViewMode="app"
      initialTab="connections"
      session={{ label: session.label, role: session.role, journeys: session.journeys }}
    />
  );
}

