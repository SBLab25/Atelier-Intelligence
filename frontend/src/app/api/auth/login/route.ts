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
    let identifier = "";
    let password = "";
    let isSignUp = false;
    let fullName = "";
    let email = "";
    let nextTarget = "/dashboard";

    const contentType = request.headers.get("content-type") || "";
    const acceptHeader = request.headers.get("accept") || "";
    const isHtmlNav = acceptHeader.includes("text/html") && !contentType.includes("application/json");

    if (contentType.includes("application/json")) {
      const body = await request.json().catch(() => ({}));
      identifier = String(body.identifier ?? body.username ?? body.email ?? "").trim();
      password = String(body.password ?? "");
      isSignUp = Boolean(body.isSignUp);
      fullName = String(body.fullName ?? "").trim();
      email = String(body.email ?? "").trim();
      nextTarget = safeNext(String(body.next ?? "/dashboard"));
    } else {
      const formData = await request.formData().catch(() => new FormData());
      identifier = String(formData.get("identifier") ?? formData.get("username") ?? formData.get("email") ?? "").trim();
      password = String(formData.get("password") ?? "");
      isSignUp = formData.get("isSignUp") === "true";
      fullName = String(formData.get("fullName") ?? "").trim();
      email = String(formData.get("email") ?? "").trim();
      nextTarget = safeNext(String(formData.get("next") ?? "/dashboard"));
    }

    // Fallback to query params if still empty (e.g. from prefilled or redirected forms)
    if (!identifier) {
      identifier = String(request.nextUrl.searchParams.get("identifier") ?? "").trim();
    }
    if (!password) {
      password = String(request.nextUrl.searchParams.get("password") ?? "");
    }

    let config;
    try {
      config = serverConfig();
    } catch (exc) {
      if (exc instanceof ConfigError) {
        log("error", "configuration invalid", { detail: exc.problems.join("; ") });
        if (isHtmlNav) {
          return NextResponse.redirect(new URL("/login?error=service_misconfigured", request.url), 303);
        }
        return NextResponse.json(
          { ok: false, problem: localProblem("service_misconfigured", crypto.randomUUID()) },
          { status: 500 },
        );
      }
      throw exc;
    }

    const respondSuccess = async (user: { id: string; fullName?: string; username: string; role: "viewer" | "operator" | "admin"; journeys: readonly string[]; email: string }) => {
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

      if (isHtmlNav) {
        const redirectRes = NextResponse.redirect(new URL(nextTarget, request.url), 303);
        redirectRes.cookies.set(SESSION_COOKIE, value, cookieOptions());
        return redirectRes;
      }

      const response = NextResponse.json({
        ok: true,
        redirect: nextTarget,
        user: { name: user.fullName, role: user.role, email: user.email },
      });
      response.cookies.set(SESSION_COOKIE, value, cookieOptions());
      return response;
    };

    // 1. Sign Up mode
    if (isSignUp) {
      if (!identifier || !password) {
        if (isHtmlNav) return NextResponse.redirect(new URL("/login?error=missing_fields", request.url), 303);
        return NextResponse.json(
          { ok: false, fieldError: "Please enter a User ID/Email and Password to create an account." },
          { status: 400 },
        );
      }
      try {
        const user = await registerWithSupabase({
          username: identifier,
          email: email || identifier,
          password,
          fullName: fullName || identifier,
        });

        try {
          await createApiKey({
            journeyName: "*",
            description: `Primary Client Ingestion Key (${user.username})`,
          });
        } catch {
          // Best-effort auto-provisioning
        }

        return await respondSuccess(user);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        if (isHtmlNav) return NextResponse.redirect(new URL(`/login?error=${encodeURIComponent(msg)}`, request.url), 303);
        return NextResponse.json({ ok: false, fieldError: msg }, { status: 400 });
      }
    }

    // 2. Normal Sign In with Supabase
    if (identifier && password) {
      try {
        const user = await authenticateWithSupabase(identifier, password);
        if (!user) {
          if (isHtmlNav) return NextResponse.redirect(new URL("/login?error=invalid_credentials", request.url), 303);
          return NextResponse.json(
            {
              ok: false,
              fieldError: "Invalid User ID / Email or Password. Please try again or create an account.",
            },
            { status: 401 },
          );
        }

        return await respondSuccess(user);
      } catch (err: unknown) {
        log("error", "Supabase authentication error", { error: String(err) });
        if (isHtmlNav) return NextResponse.redirect(new URL("/login?error=db_error", request.url), 303);
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
    if (isHtmlNav) return NextResponse.redirect(new URL("/login?error=missing_fields", request.url), 303);
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
