/**
 * Problems and results (Spec 13, OD-135). Loaders return values instead of throwing, because a production Next.js
 * build hides the message of an error thrown on the server (F-69). Safe to import in client components.
 */
import type { components } from "./schema";

export type ApiProblemBody = components["schemas"]["Problem"];

export interface Problem {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly detail: string;
  readonly requestId: string | null;
  readonly retryAfterS: number | null;
}

export type Result<T> = { readonly ok: true; readonly data: T } | { readonly ok: false; readonly problem: Problem };

export function ok<T>(data: T): Result<T> {
  return { ok: true, data };
}

export function failed<T>(problem: Problem): Result<T> {
  return { ok: false, problem };
}

const LOCAL: Record<string, { status: number; title: string; detail: string }> = {
  backend_unreachable: {
    status: 503,
    title: "Backend unreachable",
    detail: "The CJI API did not answer. Check that cji-api is running, then retry.",
  },
  backend_timeout: {
    status: 504,
    title: "Backend timeout",
    detail: "The CJI API took too long to answer. Retry in a moment.",
  },
  unexpected_response: {
    status: 502,
    title: "Unexpected response",
    detail: "The CJI API answered in a format this page does not understand.",
  },
  service_misconfigured: {
    status: 500,
    title: "Frontend misconfigured",
    detail: "The frontend configuration is incomplete; contact the operator.",
  },
};

/** A problem produced by the frontend itself (no API body). */
export function localProblem(code: keyof typeof LOCAL, requestId: string | null = null): Problem {
  const base = LOCAL[code] ?? { status: 500, title: "Error", detail: "The request failed." };
  return { ...base, code, requestId, retryAfterS: null };
}

function isProblemBody(value: unknown): value is ApiProblemBody {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const v = value as Record<string, unknown>;
  return typeof v.code === "string" && typeof v.title === "string" && typeof v.status === "number";
}

/** The problem for a non-2xx API response. Only fields of the problem schema are kept. */
export function problemFrom(status: number, body: unknown, headers: Headers, requestId: string | null): Problem {
  const retry = Number(headers.get("retry-after"));
  const retryAfterS = Number.isFinite(retry) && retry > 0 ? Math.ceil(retry) : null;
  if (isProblemBody(body)) {
    return {
      status,
      code: body.code,
      title: body.title,
      detail: typeof body.detail === "string" ? body.detail : "",
      requestId: typeof body.request_id === "string" ? body.request_id : requestId,
      retryAfterS,
    };
  }
  return { ...localProblem("unexpected_response", requestId), retryAfterS };
}
