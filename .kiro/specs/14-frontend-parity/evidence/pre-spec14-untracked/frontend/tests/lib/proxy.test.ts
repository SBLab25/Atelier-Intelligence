// @vitest-environment node
import { NextRequest } from "next/server";

import { proxy } from "@/proxy";
import { sealSession, SESSION_COOKIE } from "@/lib/session-core";

const SECRET = "p".repeat(40);
const SESSION = { token: "cji_api_token-value-00000000000000000000", tokenId: "tok_1", label: "a", role: "viewer" as const, journeys: ["*"] };

function request(path: string, cookie?: string): NextRequest {
  return new NextRequest(new URL(path, "http://localhost:3000"), {
    headers: cookie ? { cookie: `${SESSION_COOKIE}=${cookie}` } : {},
  });
}

beforeEach(() => {
  vi.stubEnv("CJI_SESSION_SECRET", SECRET);
});

describe("proxy (authentication boundary, first layer)", () => {
  it("redirects a request without a session to the login page with next", async () => {
    const response = await proxy(request("/journeys/user_onboarding?x=1"));
    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("next")).toBe("/journeys/user_onboarding?x=1");
  });

  it.each(["/", "/runs", "/runs/abc", "/reports/r1", "/journeys"])("protects %s", async (path) => {
    const response = await proxy(request(path));
    expect(response.status).toBe(307);
  });

  it("deletes an invalid cookie while redirecting", async () => {
    const response = await proxy(request("/runs", "tampered-value"));
    expect(response.status).toBe(307);
    expect(response.headers.get("set-cookie") ?? "").toMatch(new RegExp(`${SESSION_COOKIE}=;`));
  });

  it("rejects a cookie sealed with another secret", async () => {
    const { value } = await sealSession(SESSION, "o".repeat(40));
    expect((await proxy(request("/runs", value))).status).toBe(307);
  });

  it("lets a valid session through with CSP and security headers", async () => {
    const { value } = await sealSession(SESSION, SECRET);
    const response = await proxy(request("/runs", value));
    expect(response.status).toBe(200);
    const csp = response.headers.get("content-security-policy") ?? "";
    expect(csp).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+' 'strict-dynamic'/);
    expect(csp).toContain("frame-ancestors 'none'");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
    expect(response.headers.get("x-frame-options")).toBe("DENY");
  });

  it("leaves the report route's own sandbox CSP in place", async () => {
    const { value } = await sealSession(SESSION, SECRET);
    const response = await proxy(request("/reports/user_onboarding_x", value));
    expect(response.status).toBe(200);
    expect(response.headers.get("content-security-policy")).toBeNull();
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
  });

  it("uses a fresh nonce per request", async () => {
    const a = (await proxy(request("/login"))).headers.get("content-security-policy");
    const b = (await proxy(request("/login"))).headers.get("content-security-policy");
    expect(a).not.toBe(b);
  });

  it.each(["/login", "/auth/expired"])("serves %s without a session", async (path) => {
    expect((await proxy(request(path))).status).toBe(200);
  });

  it("fails closed when the secret is missing", async () => {
    vi.stubEnv("CJI_SESSION_SECRET", "");
    const response = await proxy(request("/runs"));
    expect(response.status).toBe(500);
    expect(await response.text()).not.toContain("CJI_SESSION_SECRET");
  });
});
