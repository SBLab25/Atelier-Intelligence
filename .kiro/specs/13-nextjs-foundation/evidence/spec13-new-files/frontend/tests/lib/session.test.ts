// @vitest-environment node
import { cookieOptions, openSession, sealSession, SESSION_MAX_AGE_S } from "@/lib/session-core";

const SECRET = "k".repeat(40);
const OTHER = "x".repeat(40);
const SESSION = {
  token: "cji_api_secret-token-value-0000000000000000",
  tokenId: "tok_0123456789ab",
  label: "analyst",
  role: "viewer" as const,
  journeys: ["user_onboarding"],
};

describe("session cookie", () => {
  it("round-trips and never stores the token in clear text", async () => {
    const now = 1_800_000_000;
    const { value, expiresAt } = await sealSession(SESSION, SECRET, now);
    expect(expiresAt).toBe(now + SESSION_MAX_AGE_S);
    expect(value).not.toContain(SESSION.token);
    expect(Buffer.from(value.replaceAll(".", ""), "base64url").toString("latin1")).not.toContain("cji_api_");
    expect(await openSession(value, SECRET, now + 60)).toEqual({ ...SESSION, expiresAt });
  });

  it("rejects a cookie sealed with another key", async () => {
    const { value } = await sealSession(SESSION, OTHER);
    expect(await openSession(value, SECRET)).toBeNull();
  });

  it("rejects a tampered cookie", async () => {
    const { value } = await sealSession(SESSION, SECRET);
    const parts = value.split(".");
    const last = parts[3] ?? "";
    parts[3] = (last[0] === "A" ? "B" : "A") + last.slice(1);
    expect(await openSession(parts.join("."), SECRET)).toBeNull();
  });

  it("rejects an expired cookie", async () => {
    const now = 1_800_000_000;
    const { value } = await sealSession(SESSION, SECRET, now);
    expect(await openSession(value, SECRET, now + SESSION_MAX_AGE_S + 1)).toBeNull();
  });

  it.each([undefined, "", "not-a-jwe", "a.b.c.d.e", "x".repeat(9000)])("rejects %s", async (value) => {
    expect(await openSession(value, SECRET)).toBeNull();
  });

  it("uses HttpOnly, Secure, SameSite=Strict cookies", () => {
    expect(cookieOptions()).toEqual({ httpOnly: true, secure: true, sameSite: "strict", path: "/", maxAge: SESSION_MAX_AGE_S });
  });
});
