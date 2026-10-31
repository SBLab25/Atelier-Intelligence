// @vitest-environment node
/** Loaders: the second layer of the boundary (no session, no API call) and 401 handling (Spec 13, OD-131). */
import { friction, problemBody } from "../support/fixtures";

const redirect = vi.fn((url: string) => {
  throw new Error(`NEXT_REDIRECT ${url}`);
});
const requireSession = vi.fn();

vi.mock("next/navigation", () => ({ redirect: (url: string) => redirect(url) }));
vi.mock("@/lib/session", () => ({ requireSession: () => requireSession() }));

const SESSION = { token: "cji_api_token-value-00000000000000000000", tokenId: "tok_1", label: "a", role: "viewer", journeys: ["*"], expiresAt: 0 };

async function loaders() {
  vi.stubEnv("CJI_SESSION_SECRET", "s".repeat(40));
  vi.stubEnv("CJI_API_BASE_URL", "http://api.test");
  const config = await import("@/lib/config");
  config.resetServerConfig();
  return import("@/lib/api/loaders");
}

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>(async () =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  redirect.mockClear();
  requireSession.mockReset();
});

describe("loaders", () => {
  it("make no API call without a session", async () => {
    const { getFriction } = await loaders();
    const fetchMock = stubFetch(200, friction);
    requireSession.mockImplementation(() => redirect("/login"));
    await expect(getFriction("user_onboarding")).rejects.toThrow("NEXT_REDIRECT /login");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("return API data with the session token", async () => {
    const { getFriction } = await loaders();
    const fetchMock = stubFetch(200, friction);
    requireSession.mockResolvedValue(SESSION);
    expect(await getFriction("user_onboarding")).toEqual({ ok: true, data: friction });
    const sent = fetchMock.mock.calls[0]?.[0] as Request;
    expect(sent.url).toBe("http://api.test/api/v1/journeys/user_onboarding/friction");
    expect(sent.headers.get("authorization")).toBe(`Bearer ${SESSION.token}`);
  });

  it("end the session on an API 401", async () => {
    const { getMe } = await loaders();
    stubFetch(401, problemBody(401, "invalid_token", "Invalid token", "Revoked."));
    requireSession.mockResolvedValue(SESSION);
    await expect(getMe()).rejects.toThrow("NEXT_REDIRECT /auth/expired");
  });

  it("return other problems as values", async () => {
    const { listRuns } = await loaders();
    stubFetch(503, problemBody(503, "storage_unavailable", "Storage unavailable", "Retry later."));
    requireSession.mockResolvedValue(SESSION);
    const result = await listRuns("failed");
    expect(result.ok ? null : result.problem.code).toBe("storage_unavailable");
  });

  it("call the public health endpoint without a token", async () => {
    const { getHealth } = await loaders();
    const fetchMock = stubFetch(200, { status: "ok", version: "1.0.0", mode: "demo" });
    await getHealth();
    expect(requireSession).not.toHaveBeenCalled();
    expect((fetchMock.mock.calls[0]?.[0] as Request).headers.has("authorization")).toBe(false);
  });
});
