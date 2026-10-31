// @vitest-environment node
import { apiClient, call } from "@/lib/api/client";

import { journeys, problemBody } from "../support/fixtures";

const TOKEN = "cji_api_secret-token-value-0000000000000000";

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>(async () =>
    new Response(typeof body === "string" ? body : JSON.stringify(body), {
      status,
      headers: { "Content-Type": status < 300 ? "application/json" : "application/problem+json", ...headers },
    }),
  );
  return fetchMock;
}

function client(fetchMock: (request: Request) => Promise<Response>, token: string | undefined = TOKEN) {
  return apiClient({ baseUrl: "http://api.test", token, requestId: "req-1", timeoutMs: 1000, fetch: fetchMock as typeof fetch });
}

describe("typed client", () => {
  it("returns data and sends the bearer token and request id", async () => {
    const fetchMock = respond(200, journeys);
    const result = await call("req-1", () => client(fetchMock).GET("/api/v1/journeys", { params: { query: { limit: 200 } } }));
    expect(result).toEqual({ ok: true, data: journeys });
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request.url).toBe("http://api.test/api/v1/journeys?limit=200");
    expect(request.headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(request.headers.get("x-request-id")).toBe("req-1");
  });

  it("sends no Authorization header without a token", async () => {
    const fetchMock = respond(200, { status: "ok", version: "1.0.0", mode: "demo" });
    await call("req-1", () => client(fetchMock, "").GET("/api/v1/health"));
    expect((fetchMock.mock.calls[0]?.[0] as Request).headers.has("authorization")).toBe(false);
  });

  it.each([
    [401, "invalid_token"],
    [403, "journey_forbidden"],
    [404, "journey_not_found"],
    [422, "validation_failed"],
    [500, "internal_error"],
    [503, "storage_unavailable"],
  ])("maps a %i problem", async (status, code) => {
    const fetchMock = respond(status, problemBody(status, code, "Title", "Detail text."));
    const result = await call("req-1", () => client(fetchMock).GET("/api/v1/me"));
    expect(result).toEqual({
      ok: false,
      problem: { status, code, title: "Title", detail: "Detail text.", requestId: "req-fixture-0001", retryAfterS: null },
    });
    expect(JSON.stringify(result)).not.toContain(TOKEN);
  });

  it("keeps Retry-After for 429", async () => {
    const fetchMock = respond(429, problemBody(429, "rate_limited", "Too many requests", "Slow down."), { "Retry-After": "7" });
    const result = await call("req-1", () => client(fetchMock).GET("/api/v1/me"));
    expect(result.ok ? null : result.problem.retryAfterS).toBe(7);
  });

  it("maps a body that is not a problem", async () => {
    const fetchMock = respond(502, "<html>bad gateway</html>");
    const result = await call("req-1", () => client(fetchMock).GET("/api/v1/me"));
    expect(result.ok ? null : result.problem.code).toBe("unexpected_response");
  });

  it("maps network failures without the exception text", async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError("connect ECONNREFUSED 127.0.0.1:8006 secret-detail");
    });
    const result = await call("req-1", () => client(fetchMock).GET("/api/v1/me"));
    expect(result.ok ? null : result.problem.code).toBe("backend_unreachable");
    expect(JSON.stringify(result)).not.toContain("ECONNREFUSED");
  });

  it("maps timeouts", async () => {
    const fetchMock = vi.fn(async () => {
      throw new DOMException("The operation timed out.", "TimeoutError");
    });
    const result = await call("req-1", () => client(fetchMock).GET("/api/v1/me"));
    expect(result.ok ? null : result.problem.code).toBe("backend_timeout");
  });
});
