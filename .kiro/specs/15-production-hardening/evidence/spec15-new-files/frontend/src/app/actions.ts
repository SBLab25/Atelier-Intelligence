"use server";

import { redirect } from "next/navigation";

import { apiClient, call } from "@/lib/api/client";
import { localProblem, type Problem } from "@/lib/api/problem";
import { ConfigError, serverConfig } from "@/lib/config";
import { log } from "@/lib/log";
import { edgeHeaders } from "@/lib/request-context";
import { safeNext } from "@/lib/redirects";
import { endSession, startSession } from "@/lib/session";

export interface SignInState {
  /** A message about the token itself (shown next to the field). */
  readonly fieldError: string | null;
  /** A problem reaching or using the API (shown as a problem panel). */
  readonly problem: Problem | null;
}

const TOKEN_SHAPE = /^cji_api_[A-Za-z0-9_-]{16,120}$/;

/**
 * Sign in with an API token (Spec 13, OD-130). The token is checked with GET /api/v1/me on the server and stored
 * only inside the encrypted HttpOnly session cookie. It is never echoed back to the page.
 */
export async function signIn(_previous: SignInState, form: FormData): Promise<SignInState> {
  const token = String(form.get("token") ?? "").trim();
  const next = safeNext(String(form.get("next") ?? ""));
  if (!TOKEN_SHAPE.test(token)) {
    return { fieldError: "Enter an API token. It starts with cji_api_ (create one with cji-api-token create).", problem: null };
  }
  const requestId = crypto.randomUUID();
  let config;
  try {
    config = serverConfig();
  } catch (exc) {
    if (exc instanceof ConfigError) {
      log("error", "configuration invalid", { detail: exc.problems.join("; ") });
      return { fieldError: null, problem: localProblem("service_misconfigured", requestId) };
    }
    throw exc;
  }
  const edge = await edgeHeaders(config.trustedProxyHops);
  const api = apiClient({ baseUrl: config.apiBaseUrl, token, requestId, timeoutMs: config.timeoutMs, ...edge });
  const result = await call(requestId, () => api.GET("/api/v1/me"));
  log("info", "sign-in", { status: result.ok ? 200 : result.problem.status, request_id: requestId });
  if (!result.ok) {
    if (result.problem.status === 401) {
      return { fieldError: "This token is not valid, has expired or was revoked.", problem: null };
    }
    return { fieldError: null, problem: result.problem };
  }
  const me = result.data;
  await startSession({ token, tokenId: me.token_id, label: me.label, role: me.role, journeys: me.journeys });
  redirect(next);
}

/** Sign out: delete the session cookie (Server Actions check the Origin header; the cookie is SameSite=Strict). */
export async function signOut(): Promise<void> {
  await endSession();
  redirect("/login");
}
