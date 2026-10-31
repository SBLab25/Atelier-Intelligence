"use server";

import { redirect } from "next/navigation";

import { apiClient, call } from "@/lib/api/client";
import { localProblem, type Problem } from "@/lib/api/problem";
import { ConfigError, serverConfig } from "@/lib/config";
import { log } from "@/lib/log";
import { edgeHeaders } from "@/lib/request-context";
import { safeNext } from "@/lib/redirects";
import { endSession, startSession } from "@/lib/session";
import { authenticateWithSupabase, registerWithSupabase } from "@/lib/supabase-auth";

export interface SignInState {
  /** A message about credentials (shown next to the field). */
  readonly fieldError: string | null;
  /** A problem reaching or using the API or DB (shown as a problem panel). */
  readonly problem: Problem | null;
}

const MASTER_TOKEN = process.env.CJI_INTERNAL_OPERATOR_TOKEN || "session_operator_key";
const TOKEN_SHAPE = /^cji_api_[A-Za-z0-9_-]{16,120}$/;

/**
 * Sign in with Supabase ID / Email and Password.
 * Supports fallback to API token if explicitly provided.
 */
export async function signIn(_previous: SignInState, form: FormData): Promise<SignInState> {
  const next = safeNext(String(form.get("next") ?? ""));
  const identifier = String(form.get("identifier") ?? form.get("email") ?? form.get("username") ?? "").trim();
  const password = String(form.get("password") ?? "");
  const isSignUp = form.get("isSignUp") === "true";
  const fullName = String(form.get("fullName") ?? "").trim();
  const legacyToken = String(form.get("token") ?? "").trim();

  // 1. If ID and Password are provided -> Supabase Auth
  if (identifier && password) {
    try {
      if (isSignUp) {
        const user = await registerWithSupabase({
          username: identifier,
          email: form.get("email") ? String(form.get("email")).trim() : identifier,
          password,
          fullName,
        });
        await startSession({
          token: MASTER_TOKEN,
          tokenId: user.id,
          label: user.fullName || user.username,
          role: user.role,
          journeys: user.journeys,
        });
        redirect(next);
      }

      const user = await authenticateWithSupabase(identifier, password);
      if (!user) {
        return {
          fieldError: "Invalid User ID / Email or Password. Please try again or create an account.",
          problem: null,
        };
      }

      await startSession({
        token: MASTER_TOKEN,
        tokenId: user.id,
        label: user.fullName || user.username,
        role: user.role,
        journeys: user.journeys,
      });
      redirect(next);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("NEXT_REDIRECT")) {
        throw err;
      }
      log("error", "Supabase authentication failed", { error: msg });
      return {
        fieldError: msg.includes("already taken") || msg.includes("already exists") ? msg : "Sign-in failed. Please verify your credentials.",
        problem: null,
      };
    }
  }

  // 2. Legacy API token handling (for backward compatibility / unit tests)
  if (legacyToken) {
    if (!TOKEN_SHAPE.test(legacyToken)) {
      return { fieldError: "This token is not valid, has expired or was revoked.", problem: null };
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
    const api = apiClient({ baseUrl: config.apiBaseUrl, token: legacyToken, requestId, timeoutMs: config.timeoutMs, ...edge });
    const result = await call(requestId, () => api.GET("/api/v1/me"));
    log("info", "sign-in", { status: result.ok ? 200 : result.problem.status, request_id: requestId });
    if (!result.ok) {
      if (result.problem.status === 401) {
        return { fieldError: "This token is not valid, has expired or was revoked.", problem: null };
      }
      return { fieldError: null, problem: result.problem };
    }
    const me = result.data;
    await startSession({ token: legacyToken, tokenId: me.token_id, label: me.label, role: me.role, journeys: me.journeys });
    redirect(next);
  }

  return {
    fieldError: "Please enter your User ID or Email, and Password.",
    problem: null,
  };
}

/** Sign out: delete the session cookie. */
export async function signOut(): Promise<void> {
  await endSession();
  redirect("/signed-out");
}
