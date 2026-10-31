/**
 * Request proxy (Spec 13, OD-131, OD-136): the first layer of the authentication boundary and the security headers.
 * Pages without a valid session cookie are redirected to /login before anything renders; every data loader checks
 * the session again (second layer).
 */
import { NextResponse, type NextRequest } from "next/server";

import { ConfigError, parseConfig } from "./lib/config-core";
import { contentSecurityPolicy, newNonce, STATIC_HEADERS } from "./lib/security-headers";
import { openSession, SESSION_COOKIE } from "./lib/session-core";

/** Paths that render without a session. */
export const PUBLIC_PATHS: ReadonlySet<string> = new Set(["/login", "/auth/expired"]);

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

  if (!PUBLIC_PATHS.has(pathname)) {
    let secret: string;
    try {
      secret = parseConfig(process.env).sessionSecret;
    } catch (exc) {
      if (exc instanceof ConfigError) {
        console.error(`[cji-frontend] ${exc.message}`);
        const response = new NextResponse("The frontend configuration is incomplete; see the server log.", {
          status: 500,
          headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
        });
        return withSecurityHeaders(response, csp);
      }
      throw exc;
    }
    const raw = request.cookies.get(SESSION_COOKIE)?.value;
    const session = await openSession(raw, secret);
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
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Cache-Control", "no-store");
  const ownCsp = OWN_CSP_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  return withSecurityHeaders(response, ownCsp ? null : csp);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
