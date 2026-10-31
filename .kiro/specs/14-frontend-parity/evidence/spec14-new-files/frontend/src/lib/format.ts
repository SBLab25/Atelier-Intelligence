/**
 * Number formatting for display (Spec 14, requirements §4). This is the only place values from the API are rounded:
 * percentages to 1 decimal, counts as integers with thousands separators, durations in seconds with 1 decimal,
 * fractions (confidence) to 2 decimals. Nothing is recalculated (OD-140).
 */
const COUNT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

function finite(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function pct(value: number | null | undefined): string {
  return finite(value) ? `${value.toFixed(1)}%` : "—";
}

export function count(value: number | null | undefined): string {
  return finite(value) ? COUNT.format(Math.round(value)) : "—";
}

export function seconds(ms: number | null | undefined): string {
  return finite(ms) ? `${(ms / 1000).toFixed(1)} s` : "—";
}

export function fraction(value: number | null | undefined): string {
  return finite(value) ? value.toFixed(2) : "—";
}

export function decimal(value: number | null | undefined, digits = 2): string {
  return finite(value) ? value.toFixed(digits) : "—";
}

/** Bar width for drawing only (0-100), relative to the largest value; the numbers are always shown as text. */
export function barWidth(value: number, max: number): number {
  if (!finite(value) || !finite(max) || max <= 0 || value <= 0) {
    return 0;
  }
  return Math.min(100, Math.round((value / max) * 100));
}

export function usd(value: number | null | undefined): string {
  return finite(value) ? `$${value.toFixed(4)}` : "—";
}
