import type { Metadata } from "next";
import { CockpitApp } from "@/cockpit/App";

export const metadata: Metadata = {
  title: "Cockpit · CJI Atelier",
  description: "Tactile Bento Modular System Workbench.",
};

export default function CockpitPage() {
  return <CockpitApp initialViewMode="app" initialTab="dashboard" />;
}

