import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import { ConfigError, serverConfig } from "./config";
import { log } from "./log";
import { cookieOptions, openSessionWithRotation, sealSession, SESSION_COOKIE, type Session } from "./session-core";

export type { Session } from "./session-core";

/** The current session (read once per request), or null. */
export const getSession = cache(async (): Promise<Session | null> => {
  let keys: { secret: string; previous: string | null };
  try {
    const config = serverConfig();
    keys = { secret: config.sessionSecret, previous: config.sessionSecretPrevious };
  } catch (exc) {
    if (exc instanceof ConfigError) {
      log("error", "configuration invalid", { detail: exc.problems.join("; ") });
      return null; // no valid configuration, no session: every protected page goes to /login
    }
    throw exc;
  }
  const store = await cookies();
  // The proxy re-issues cookies sealed with the previous key; here the session is only read.
  return (await openSessionWithRotation(store.get(SESSION_COOKIE)?.value, keys.secret, keys.previous)).session;
});

/** The current session; without one the request is sent to the login page (second layer behind the proxy). */
export async function requireSession(): Promise<Session> {
  const session = await getSession();
  if (!session) {
    redirect("/login");
  }
  return session;
}

/** Start a session (Server Actions only: cookies can be written there, not while rendering). */
export async function startSession(session: Omit<Session, "expiresAt">): Promise<void> {
  const { value } = await sealSession(session, serverConfig().sessionSecret);
  const store = await cookies();
  store.set(SESSION_COOKIE, value, cookieOptions());
}

/** End the session (Server Actions and route handlers only). */
export async function endSession(): Promise<void> {
  const store = await cookies();
  store.delete({ name: SESSION_COOKIE, path: "/" });
}
