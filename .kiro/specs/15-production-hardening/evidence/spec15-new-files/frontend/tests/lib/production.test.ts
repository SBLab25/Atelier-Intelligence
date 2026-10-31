/**
 * Spec 15: trace context, trusted client address, JSON log lines, configuration rules, session key rotation and the
 * headers the API client sends.
 */
import { describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api/client";
import { clientAddress } from "@/lib/client-address";
import { ConfigError, parseConfig } from "@/lib/config-core";
import { formatLine } from "@/lib/log";
import { openSession, openSessionWithRotation, resealSession, sealSession } from "@/lib/session-core";
import { childTraceparent, edgeTrace, formatTraceparent, parseTraceparent } from "@/lib/trace";

const OLD = "o".repeat(40);
const NEW = "n".repeat(40);
const SESSION = { token: "cji_api_" + "t".repeat(43), tokenId: "tok_1", label: "x", role: "viewer" as const, journeys: ["j"] };

describe("trace context", () => {
  it("parses valid headers and rejects malformed or zero ids", () => {
    const header = `00-${"ab".repeat(16)}-${"cd".repeat(8)}-01`;
    expect(parseTraceparent(header)).toEqual({ traceId: "ab".repeat(16), spanId: "cd".repeat(8) });
    for (const bad of [null, "", `01-${header.slice(3)}`, `00-${"0".repeat(32)}-${"cd".repeat(8)}-01`, "00-x"]) {
      expect(parseTraceparent(bad)).toBeNull();
    }
  });

  it("keeps the incoming trace for child calls and starts one when absent", () => {
    const edge = edgeTrace(`00-${"12".repeat(16)}-${"34".repeat(8)}-01`);
    expect(edge.traceId).toBe("12".repeat(16));
    const child = parseTraceparent(childTraceparent(formatTraceparent(edge)));
    expect(child?.traceId).toBe(edge.traceId);
    expect(child?.spanId).not.toBe(edge.spanId);
    expect(parseTraceparent(childTraceparent(null))).not.toBeNull();
  });
});

describe("client address", () => {
  it("trusts X-Forwarded-For only for the configured number of proxies", () => {
    expect(clientAddress("203.0.113.9", 0)).toBeNull();
    expect(clientAddress("203.0.113.9", 1)).toBe("203.0.113.9");
    expect(clientAddress("198.51.100.1, 203.0.113.9", 1)).toBe("203.0.113.9");
    expect(clientAddress("198.51.100.1, 203.0.113.9", 2)).toBe("198.51.100.1");
    expect(clientAddress("203.0.113.9", 2)).toBeNull();
    expect(clientAddress("<script>", 1)).toBeNull();
    expect(clientAddress(null, 1)).toBeNull();
  });
});

describe("log lines", () => {
  it("writes one JSON object with named fields in production", () => {
    const line = JSON.parse(formatLine("info", "sign-in", { status: 200, request_id: "r1", skipped: undefined }, true,
      new Date("2026-10-29T00:00:00Z"))) as Record<string, unknown>;
    expect(line).toEqual({ ts: "2026-10-29T00:00:00.000Z", level: "INFO", logger: "cji.frontend", message: "sign-in",
      service: "cji-frontend", status: 200, request_id: "r1" });
  });

  it("keeps the readable prefix outside production", () => {
    expect(formatLine("error", "api", { status: 503 }, false)).toBe("[cji-frontend] api status=503");
  });
});

describe("configuration (Spec 15 rules)", () => {
  const base = { CJI_SESSION_SECRET: NEW };

  it("accepts a previous session key and proxy hops", () => {
    const config = parseConfig({ ...base, CJI_SESSION_SECRET_PREVIOUS: OLD, CJI_FRONTEND_TRUSTED_PROXY_HOPS: "1" });
    expect(config.sessionSecretPrevious).toBe(OLD);
    expect(config.trustedProxyHops).toBe(1);
    expect(parseConfig(base).sessionSecretPrevious).toBeNull();
  });

  it.each([
    [{ CJI_SESSION_SECRET_PREVIOUS: "short" }, "CJI_SESSION_SECRET_PREVIOUS"],
    [{ CJI_SESSION_SECRET_PREVIOUS: NEW }, "CJI_SESSION_SECRET_PREVIOUS"],
    [{ CJI_FRONTEND_TRUSTED_PROXY_HOPS: "9" }, "CJI_FRONTEND_TRUSTED_PROXY_HOPS"],
    [{ NODE_ENV: "production", CJI_API_BASE_URL: "http://api.example.com" }, "must use https in production"],
  ])("rejects %o", (extra, message) => {
    expect(() => parseConfig({ ...base, ...extra })).toThrow(ConfigError);
    expect(() => parseConfig({ ...base, ...extra })).toThrow(message);
  });

  it("allows plain http to a loopback API in production", () => {
    expect(parseConfig({ ...base, NODE_ENV: "production", CJI_API_BASE_URL: "http://127.0.0.1:8006" }).apiBaseUrl).toBe(
      "http://127.0.0.1:8006",
    );
  });
});

describe("session key rotation", () => {
  it("opens cookies sealed with the previous key and asks for a re-issue", async () => {
    const now = 1_800_000_000;
    const { value } = await sealSession(SESSION, OLD, now);
    expect(await openSession(value, NEW, now)).toBeNull();
    const opened = await openSessionWithRotation(value, NEW, OLD, now);
    expect(opened.reissue).toBe(true);
    expect(opened.session?.tokenId).toBe("tok_1");
    const resealed = await resealSession(opened.session!, NEW, now + 60);
    const again = await openSessionWithRotation(resealed, NEW, OLD, now + 60);
    expect(again.reissue).toBe(false);
    expect(again.session?.expiresAt).toBe(opened.session?.expiresAt);
  });

  it("refuses cookies under neither key", async () => {
    const { value } = await sealSession(SESSION, "x".repeat(40));
    expect(await openSessionWithRotation(value, NEW, OLD)).toEqual({ session: null, reissue: false });
    expect(await openSessionWithRotation(value, NEW, null)).toEqual({ session: null, reissue: false });
  });
});

describe("API client headers", () => {
  it("sends a child traceparent and the trusted client address", async () => {
    const seen: Headers[] = [];
    const fetchSpy = vi.fn(async (input: RequestInfo | URL) => {
      seen.push((input as Request).headers);
      return new Response(JSON.stringify({ status: "ok", version: "1", mode: "demo" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    const parent = `00-${"56".repeat(16)}-${"78".repeat(8)}-01`;
    const api = apiClient({ baseUrl: "http://127.0.0.1:1", requestId: "req-1", timeoutMs: 1000,
      fetch: fetchSpy as unknown as typeof fetch, traceparent: parent, forwardedFor: "203.0.113.9" });
    await api.GET("/api/v1/health");
    const headers = seen[0]!;
    expect(parseTraceparent(headers.get("traceparent"))?.traceId).toBe("56".repeat(16));
    expect(headers.get("traceparent")).not.toBe(parent);
    expect(headers.get("x-forwarded-for")).toBe("203.0.113.9");
    const plain = apiClient({ baseUrl: "http://127.0.0.1:1", requestId: "req-2", timeoutMs: 1000,
      fetch: fetchSpy as unknown as typeof fetch });
    await plain.GET("/api/v1/health");
    expect(seen[1]!.get("x-forwarded-for")).toBeNull();
    expect(parseTraceparent(seen[1]!.get("traceparent"))).not.toBeNull();
  });
});
