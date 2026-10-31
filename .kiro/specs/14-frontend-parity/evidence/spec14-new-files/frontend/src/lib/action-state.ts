import type { Problem } from "./api/problem";

/**
 * The value a Server Action returns to its form (Spec 14, OD-151): nothing yet, a refusal with a message for the
 * form (fieldError) or an API problem, or the result. Serialisable; safe in client components.
 */
export type ActionState<T> =
  | { readonly status: "idle" }
  | { readonly status: "error"; readonly fieldError: string | null; readonly problem: Problem | null }
  | { readonly status: "done"; readonly data: T };

export const IDLE = { status: "idle" } as const;

export function fieldError(message: string): { readonly status: "error"; readonly fieldError: string; readonly problem: null } {
  return { status: "error", fieldError: message, problem: null };
}

export function problemState(problem: Problem): { readonly status: "error"; readonly fieldError: null; readonly problem: Problem } {
  return { status: "error", fieldError: null, problem };
}

/** An optional whole number from a form field: undefined when empty, null when invalid or out of range. */
export function optionalInt(raw: FormDataEntryValue | null, min: number, max: number): number | undefined | null {
  const text = typeof raw === "string" ? raw.trim() : "";
  if (text === "") {
    return undefined;
  }
  if (!/^\d{1,6}$/.test(text)) {
    return null;
  }
  const value = Number(text);
  return value >= min && value <= max ? value : null;
}

export const RUN_ID = /^[A-Za-z0-9-]{1,64}$/;
export const JOURNEY_ID = /^[^\x00-\x1f\x7f/]{1,128}$/;
