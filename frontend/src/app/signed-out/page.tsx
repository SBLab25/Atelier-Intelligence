import type { Metadata } from "next";
import { SignedOutClient } from "./SignedOutClient";

export const metadata: Metadata = {
  title: "Signed Out · CJI",
  description: "Session concluded. Workstation tokens securely de-authenticated.",
};

export default function Page() {
  return (
    <main id="main" className="min-h-screen bg-background">
      <SignedOutClient />
    </main>
  );
}

