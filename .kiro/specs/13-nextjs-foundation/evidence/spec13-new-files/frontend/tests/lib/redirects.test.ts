// @vitest-environment node
import { safeNext } from "@/lib/redirects";

describe("safeNext", () => {
  it.each([
    ["/journeys", "/journeys"],
    ["/journeys/user_onboarding?x=1", "/journeys/user_onboarding?x=1"],
    ["%2Fruns%3Fstatus%3Dfailed", "/runs?status=failed"],
    ["/runs#top", "/runs"],
  ])("keeps the same-origin path %s", (raw, expected) => {
    expect(safeNext(raw)).toBe(expected);
  });

  it.each([
    null,
    undefined,
    "",
    "journeys",
    "//evil.example",
    "/\\evil.example",
    "%2F%2Fevil.example",
    "https://evil.example/",
    "javascript:alert(1)",
    "/%0d%0aSet-Cookie:x",
    "/login",
    "/login?next=/x",
    `/${"a".repeat(600)}`,
    "%E0%A4%A",
  ])("falls back to / for %s", (raw) => {
    expect(safeNext(raw)).toBe("/");
  });
});
