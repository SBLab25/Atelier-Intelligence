import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE } from "@/lib/session-core";

/**
 * The API answered 401 for the current token (revoked, expired or unknown). Pages cannot change cookies while they
 * render, so loaders redirect here: the cookie is deleted and the user goes to the login page.
 */
export function GET(request: NextRequest): NextResponse {
  const response = NextResponse.redirect(new URL("/login?reason=expired", request.url), 303);
  response.cookies.delete({ name: SESSION_COOKIE, path: "/" });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
