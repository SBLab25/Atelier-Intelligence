import { NextResponse, type NextRequest } from "next/server";
import { cookies } from "next/headers";
import { localProblem } from "@/lib/api/problem";
import { ConfigError, serverConfig } from "@/lib/config";
import { log } from "@/lib/log";
import { safeNext } from "@/lib/redirects";
import { cookieOptions, sealSession, SESSION_COOKIE } from "@/lib/session-core";
import { authenticateWithSupabase, registerWithSupabase } from "@/lib/supabase-auth";
import { createApiKey } from "@/lib/api-keys";

const MASTER_TOKEN = process.env.CJI_INTERNAL_OPERATOR_TOKEN || "session_operator_key";

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const body = await request.json().catch(() => ({}));
    const identifier = String(body.identifier ?? body.username ?? body.email ?? "").trim();
    const password = String(body.password ?? "");
    const isSignUp = Boolean(body.isSignUp);
    const fullName = String(body.fullName ?? "").trim();
    const nextTarget = safeNext(String(body.next ?? "/dashboard"));

    let config;
    try {
      config = serverConfig();
    } catch (exc) {
      if (exc instanceof ConfigError) {
        log("error", "configuration invalid", { detail: exc.problems.join("; ") });
        return NextResponse.json(
          { ok: false, problem: localProblem("service_misconfigured", crypto.randomUUID()) },
          { status: 500 },
        );
      }
      throw exc;
    }

    // 1. Sign Up mode
    if (isSignUp) {
      if (!identifier || !password) {
        return NextResponse.json(
          { ok: false, fieldError: "Please enter a User ID/Email and Password to create an account." },
          { status: 400 },
        );
      }
      try {
        const user = await registerWithSupabase({
          username: identifier,
          email: body.email ? String(body.email).trim() : identifier,
          password,
          fullName: fullName || identifier,
        });

        // Pre-provision client ingestion key for the new user account
        try {
          await createApiKey({
            journeyName: "*",
            description: `Primary Client Ingestion Key (${user.username})`,
          });
        } catch {
          // Best-effort auto-provisioning
        }

        const { value } = await sealSession(
          {
            token: MASTER_TOKEN,
            tokenId: user.id,
            label: user.fullName || user.username,
            role: user.role,
            journeys: user.journeys,
          },
          config.sessionSecret,
        );

        const cookieStore = await cookies();
        cookieStore.set(SESSION_COOKIE, value, cookieOptions());

        const response = NextResponse.json({
          ok: true,
          redirect: nextTarget,
          user: { name: user.fullName, role: user.role, email: user.email },
        });
        response.cookies.set(SESSION_COOKIE, value, cookieOptions());
        return response;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return NextResponse.json({ ok: false, fieldError: msg }, { status: 400 });
      }
    }

    // 2. Normal Sign In with Supabase
    if (identifier && password) {
      try {
        const user = await authenticateWithSupabase(identifier, password);
        if (!user) {
          return NextResponse.json(
            {
              ok: false,
              fieldError: "Invalid User ID / Email or Password. Please try again or create an account.",
            },
            { status: 401 },
          );
        }

        const { value } = await sealSession(
          {
            token: MASTER_TOKEN,
            tokenId: user.id,
            label: user.fullName || user.username,
            role: user.role,
            journeys: user.journeys,
          },
          config.sessionSecret,
        );

        const cookieStore = await cookies();
        cookieStore.set(SESSION_COOKIE, value, cookieOptions());

        const response = NextResponse.json({
          ok: true,
          redirect: nextTarget,
          user: { name: user.fullName, role: user.role, email: user.email },
        });
        response.cookies.set(SESSION_COOKIE, value, cookieOptions());
        return response;
      } catch (err: unknown) {
        log("error", "Supabase authentication error", { error: String(err) });
        return NextResponse.json(
          {
            ok: false,
            fieldError: "Database connection failed. Please ensure Supabase is accessible.",
          },
          { status: 500 },
        );
      }
    }

    // Missing fields
    return NextResponse.json(
      { ok: false, fieldError: "Please enter your User ID or Email, and Password." },
      { status: 400 },
    );
  } catch (err) {
    log("error", "unexpected error during auth login", { error: String(err) });
    return NextResponse.json(
      {
        ok: false,
        fieldError: "An unexpected error occurred during sign-in. Please try again.",
      },
      { status: 500 },
    );
  }
}
