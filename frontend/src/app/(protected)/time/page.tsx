import type { Metadata } from "next";
import { CockpitApp } from "@/cockpit/App";

export const metadata: Metadata = {
  title: "Time Operations · CJI Atelier",
  description: "Tactile circular time dial and session logging.",
};

export default function TimePage() {
  return <CockpitApp initialViewMode="app" initialTab="time" />;
}

