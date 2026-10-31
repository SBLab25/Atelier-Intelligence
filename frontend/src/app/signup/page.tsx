import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { safeNext } from "@/lib/redirects";
import { getSession } from "@/lib/session";
import { LoginScreen } from "@/cockpit/components/screens/LoginScreen";

export const metadata: Metadata = {
  title: "Create Account · CJI Atelier",
  description: "Register for Customer Journey Intelligence & Quantitative Operations Cockpit.",
};

export default async function SignUpPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const nextParam = typeof params.next === "string" ? params.next : null;
  const next = nextParam ? safeNext(nextParam) : "/dashboard";

  if (await getSession()) {
    redirect(next);
  }

  return (
    <main id="main" tabIndex={-1} className="min-h-screen w-full bg-background flex items-center justify-center">
      <LoginScreen initialMode="signup" next={next} />
    </main>
  );
}

