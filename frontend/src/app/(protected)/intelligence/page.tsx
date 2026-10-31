import type { Metadata } from "next";
import { IntelligenceHubScreen } from "@/cockpit/components/screens/IntelligenceHubScreen";

export const metadata: Metadata = {
  title: "Intelligence Hub · CJI Atelier",
  description: "AI-driven scenario simulation and milestone confidence synthesizer.",
};

export default function IntelligencePage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <IntelligenceHubScreen />
    </div>
  );
}

