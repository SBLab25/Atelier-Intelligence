/**
 * Request proxy (Spec 13, OD-131, OD-136): the first layer of the authentication boundary and the security headers.
 * Pages without a valid session cookie are redirected to /login before anything renders; every data loader checks
 * the session again (second layer).
 */
import { NextResponse, type NextRequest } from "next/server";

import { ConfigError, parseConfig } from "./lib/config-core";
import { log } from "./lib/log";
import { contentSecurityPolicy, newNonce, STATIC_HEADERS } from "./lib/security-headers";
import { cookieOptions, openSessionWithRotation, resealSession, SESSION_COOKIE, type Session } from "./lib/session-core";
import { edgeTrace, formatTraceparent } from "./lib/trace";

/** Paths that render without a session (health checks: Spec 15, public landing and signout). */
export const PUBLIC_PATHS: ReadonlySet<string> = new Set([
  "/login",
  "/auth/expired",
  "/healthz",
  "/readyz",
  "/landing",
  "/signed-out",
  "/api/analytics",
  "/api/auth/login",
  "/api/auth/signout",
]);

/** Routes that set their own, stricter Content-Security-Policy (report HTML: no scripts, sandboxed). */
const OWN_CSP_PREFIXES = ["/reports/"] as const;

function withSecurityHeaders(response: NextResponse, csp: string | null): NextResponse {
  if (csp) {
    response.headers.set("Content-Security-Policy", csp);
  }
  for (const [name, value] of Object.entries(STATIC_HEADERS)) {
    response.headers.set(name, value);
  }
  return response;
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const nonce = newNonce();
  const csp = contentSecurityPolicy(nonce, process.env.NODE_ENV === "development");
  const { pathname, search } = request.nextUrl;
  let reissue: { session: Session; secret: string } | null = null;

  if (!PUBLIC_PATHS.has(pathname)) {
    let secret: string;
    let previous: string | null;
    try {
      const config = parseConfig(process.env);
      secret = config.sessionSecret;
      previous = config.sessionSecretPrevious;
    } catch (exc) {
      if (exc instanceof ConfigError) {
        log("error", "configuration invalid", { detail: exc.problems.join("; ") });
        const response = new NextResponse("The frontend configuration is incomplete; see the server log.", {
          status: 500,
          headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
        });
        return withSecurityHeaders(response, csp);
      }
      throw exc;
    }
    const raw = request.cookies.get(SESSION_COOKIE)?.value;
    const opened = await openSessionWithRotation(raw, secret, previous);
    const session = opened.session;
    if (session && opened.reissue) {
      reissue = { session, secret };
    }
    if (!session) {
      const login = new URL("/login", request.url);
      if (pathname !== "/") {
        login.searchParams.set("next", pathname + search);
      }
      const response = NextResponse.redirect(login, 307);
      if (raw !== undefined) {
        response.cookies.delete({ name: SESSION_COOKIE, path: "/" });
      }
      response.headers.set("Cache-Control", "no-store");
      return withSecurityHeaders(response, csp);
    }
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  // Spec 15 (OD-161): one trace per page request; API calls made while rendering are its child spans.
  requestHeaders.set("traceparent", formatTraceparent(edgeTrace(request.headers.get("traceparent"))));

  if (process.env.NODE_ENV === "development") {
    const rawOrigin = request.headers.get("origin");
    if (!rawOrigin || rawOrigin === "null") {
      const devHost = request.headers.get("x-forwarded-host") || request.headers.get("host");
      if (devHost) {
        requestHeaders.set("origin", `http://${devHost}`);
      }
    }
  }
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Cache-Control", "no-store");
  if (reissue) {
    // Spec 15 (OD-163): the cookie was sealed with the previous key; re-seal it with the current one.
    const remaining = Math.max(1, reissue.session.expiresAt - Math.floor(Date.now() / 1000));
    response.cookies.set(SESSION_COOKIE, await resealSession(reissue.session, reissue.secret), cookieOptions(remaining));
  }
  const ownCsp = OWN_CSP_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  return withSecurityHeaders(response, ownCsp ? null : csp);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
