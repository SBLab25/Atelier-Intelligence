/**
 * Typed /api/v1 client (Spec 13, OD-132, OD-141). Server-only: it attaches the session's bearer token. Every call
 * returns a Result; network failures and timeouts become local problems without exception text.
 */
import createClient, { type Client } from "openapi-fetch";

import { childTraceparent } from "../trace";
import { failed, localProblem, ok, problemFrom, type Result } from "./problem";
import type { paths } from "./schema";

export type ApiClient = Client<paths>;

export interface ClientOptions {
  readonly baseUrl: string;
  readonly token?: string | undefined;
  readonly requestId: string;
  readonly timeoutMs: number;
  readonly fetch?: typeof globalThis.fetch;
  /** Spec 15: the page request's trace; each call is sent as a child span of it (a new trace when absent). */
  readonly traceparent?: string | null | undefined;
  /** Spec 15: the browser's address through trusted proxies, forwarded as X-Forwarded-For (omitted when null). */
  readonly forwardedFor?: string | null | undefined;
}

export function apiClient(options: ClientOptions): ApiClient {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Request-ID": options.requestId,
    traceparent: childTraceparent(options.traceparent),
  };
  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }
  if (options.forwardedFor) {
    headers["X-Forwarded-For"] = options.forwardedFor;
  }
  return createClient<paths>({
    baseUrl: options.baseUrl,
    headers,
    cache: "no-store",
    fetch: (request: Request) => (options.fetch ?? globalThis.fetch)(request, { signal: AbortSignal.timeout(options.timeoutMs) }),
  });
}

interface FetchOutcome<T> {
  readonly data?: T;
  readonly error?: unknown;
  readonly response: Response;
}

/** Run one typed call and turn its outcome into a Result. */
export async function call<T>(requestId: string, run: () => Promise<FetchOutcome<T>>): Promise<Result<T>> {
  let outcome: FetchOutcome<T>;
  try {
    outcome = await run();
  } catch (exc) {
    const timedOut = exc instanceof DOMException && (exc.name === "TimeoutError" || exc.name === "AbortError");
    return failed(localProblem(timedOut ? "backend_timeout" : "backend_unreachable", requestId));
  }
  const { response } = outcome;
  if (response.ok) {
    if (outcome.data === undefined) {
      return failed(localProblem("unexpected_response", requestId));
    }
    return ok(outcome.data);
  }
  return failed(problemFrom(response.status, outcome.error, response.headers, requestId));
}
