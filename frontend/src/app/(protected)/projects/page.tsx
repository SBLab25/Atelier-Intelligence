import type { Metadata } from "next";
import { CockpitApp } from "@/cockpit/App";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = {
  title: "Projects & Milestones · CJI Atelier",
  description: "Sprint deliverables and journey engineering tasks.",
};

  export default async function ProjectsPage() {
    const session = await requireSession();
    return (
      <CockpitApp
        initialViewMode="app"
        initialTab="projects"
        session={{ label: session.label, role: session.role, journeys: session.journeys }}
      />
    );
  }
