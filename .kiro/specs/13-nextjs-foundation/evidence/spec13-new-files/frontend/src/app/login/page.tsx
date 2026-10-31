import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { safeNext } from "@/lib/redirects";
import { getSession } from "@/lib/session";

import { LoginForm } from "./LoginForm";

export const metadata: Metadata = { title: "Sign in · CJI" };

const REASONS: Readonly<Record<string, string>> = {
  expired: "Your session ended or your token is no longer accepted. Sign in again.",
};

export default async function LoginPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const next = safeNext(typeof params.next === "string" ? params.next : null);
  if (await getSession()) {
    redirect(next);
  }
  const reason = typeof params.reason === "string" ? REASONS[params.reason] : undefined;
  return (
    <main id="main" tabIndex={-1} className="login">
      <h1>Customer Journey Intelligence</h1>
      <p>Sign in with your API token to see journeys, friction and workflow status.</p>
      {reason ? (
        <p className="notice" role="status">
          {reason}
        </p>
      ) : null}
      <LoginForm next={next} />
    </main>
  );
}
