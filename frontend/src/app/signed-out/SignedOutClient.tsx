"use client";

import { SignedOutScreen } from "@/cockpit/components/screens/SignedOutScreen";
import { currentUser } from "@/cockpit/data/mockData";

export function SignedOutClient() {
  return (
    <SignedOutScreen
      lastUser={currentUser}
      onSignInAgain={() => {
        window.location.href = "/login";
      }}
      onExploreCockpit={() => {
        window.location.href = "/dashboard";
      }}
    />
  );
}
