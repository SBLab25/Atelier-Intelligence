import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { safeNext } from "@/lib/redirects";
import { getSession } from "@/lib/session";
import { LoginScreen } from "@/cockpit/components/screens/LoginScreen";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Sign in · CJI Atelier",
  description: "Customer Journey Intelligence & Quantitative Sprint Cockpit Workspace Login.",
};

export default async function LoginPage({
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
      <LoginScreen next={next} />
    </main>
  );
}
