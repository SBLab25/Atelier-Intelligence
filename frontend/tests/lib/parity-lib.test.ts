/** Spec 14 helpers: display formatting (requirements §4), roles, idempotency keys, form parsing. */
import { optionalInt } from "@/lib/action-state";
import { barWidth, count, decimal, fraction, pct, seconds, usd } from "@/lib/format";
import { isKey, newKey } from "@/lib/idempotency";
import { atLeast, roleHint } from "@/lib/roles";
import { parseWindow } from "@/views/journeys";

describe("format", () => {
  it("rounds only for display", () => {
    expect(pct(62.84)).toBe("62.8%");
    expect(pct(0)).toBe("0.0%");
    expect(pct(null)).toBe("—");
    expect(count(1640)).toBe("1,640");
    expect(count(1639.6)).toBe("1,640");
    expect(seconds(5200)).toBe("5.2 s");
    expect(fraction(0.9)).toBe("0.90");
    expect(decimal(2.105, 1)).toBe("2.1");
    expect(usd(0.0021)).toBe("$0.0021");
    expect(pct(Number.NaN)).toBe("—");
  });

  it("draws bars relative to the largest value", () => {
    expect(barWidth(1000, 2000)).toBe(50);
    expect(barWidth(0, 2000)).toBe(0);
    expect(barWidth(5, 0)).toBe(0);
    expect(barWidth(3000, 2000)).toBe(100);
  });
});

describe("roles", () => {
  it("orders viewer < operator < admin", () => {
    expect(atLeast("viewer", "operator")).toBe(false);
    expect(atLeast("operator", "operator")).toBe(true);
    expect(atLeast("admin", "operator")).toBe(true);
    expect(atLeast("operator", "admin")).toBe(false);
    expect(roleHint("admin")).toContain("Requires the admin role");
  });
});

describe("idempotency keys", () => {
  it("match the API's key format", () => {
    const key = newKey();
    expect(isKey(key)).toBe(true);
    expect(newKey()).not.toBe(key);
    expect(isKey("short")).toBe(false);
    expect(isKey("has space in it")).toBe(false);
    expect(isKey(null)).toBe(false);
  });
});

describe("form parsing", () => {
  it("reads optional whole numbers in range", () => {
    expect(optionalInt("", 1, 365)).toBeUndefined();
    expect(optionalInt(null, 1, 365)).toBeUndefined();
    expect(optionalInt(" 30 ", 1, 365)).toBe(30);
    expect(optionalInt("0", 1, 365)).toBeNull();
    expect(optionalInt("1.5", 1, 365)).toBeNull();
    expect(optionalInt("400", 1, 365)).toBeNull();
  });

  it("parses the journey window from the query string", () => {
    expect(parseWindow("7", undefined)).toEqual({ days: 7 });
    expect(parseWindow(undefined, "60")).toEqual({ minutes: 60 });
    expect(parseWindow("7", "60")).toEqual({ minutes: 60 });
    expect(parseWindow("999", undefined)).toEqual({});
    expect(parseWindow(["7"], undefined)).toEqual({});
    expect(parseWindow("x", "y")).toEqual({});
  });
});
