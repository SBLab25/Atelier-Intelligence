import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { ConfigError, serverConfig } from "../config";
import { requireSession } from "../session";
import { apiClient, call, type ApiClient } from "./client";
import { failed, localProblem, type Result } from "./problem";
import type { components } from "./schema";

/**
 * One typed loader per view (Spec 13, design §4). Every loader except `getHealth` requires the session; an API 401
 * ends it through `/auth/expired` (cookies cannot be changed while a page renders).
 */

type Schemas = components["schemas"];
export type Health = Schemas["Health"];
export type HealthDetails = Schemas["HealthDetails"];
export type Me = Schemas["Me"];
export type Journey = Schemas["Journey"];
export type JourneyPage = Schemas["Page_Journey_"];
export type Metrics = Schemas["Metrics"];
export type Friction = Schemas["Friction"];
export type RunSummaryPage = Schemas["Page_RunSummary_"];
export type Run = Schemas["Run"];
export type Report = Schemas["Report"];
export type RunStatus = Schemas["RunSummary"]["status"];

export const RUN_STATUSES: readonly RunStatus[] = ["running", "awaiting_approval", "approved", "completed", "failed"];

/** One request id per page request, sent as X-Request-ID on every API call (OD-141). */
export const pageRequestId = cache((): string => crypto.randomUUID());

interface Context {
  readonly api: ApiClient;
  readonly requestId: string;
}

async function context(withToken: boolean): Promise<Context | Result<never>> {
  const requestId = pageRequestId();
  let config;
  try {
    config = serverConfig();
  } catch (exc) {
    if (exc instanceof ConfigError) {
      console.error(`[cji-frontend] ${exc.message}`);
      return failed(localProblem("service_misconfigured", requestId));
    }
    throw exc;
  }
  const token = withToken ? (await requireSession()).token : undefined;
  return { api: apiClient({ baseUrl: config.apiBaseUrl, token, requestId, timeoutMs: config.timeoutMs }), requestId };
}

function isContext(value: Context | Result<never>): value is Context {
  return "api" in value;
}

async function load<T>(withToken: boolean, label: string, run: (ctx: Context) => Promise<Result<T>>): Promise<Result<T>> {
  const ctx = await context(withToken);
  if (!isContext(ctx)) {
    return ctx;
  }
  const result = await run(ctx);
  const status = result.ok ? 200 : result.problem.status;
  console.info(`[cji-frontend] api ${label} status=${status} request_id=${ctx.requestId}`);
  if (!result.ok && result.problem.status === 401 && withToken) {
    redirect("/auth/expired");
  }
  return result;
}

export function getHealth(): Promise<Result<Health>> {
  return load(false, "GET /health", ({ api, requestId }) => call(requestId, () => api.GET("/api/v1/health")));
}

export function getHealthDetails(): Promise<Result<HealthDetails>> {
  return load(true, "GET /health/details", ({ api, requestId }) =>
    call(requestId, () => api.GET("/api/v1/health/details")),
  );
}

export function getMe(): Promise<Result<Me>> {
  return load(true, "GET /me", ({ api, requestId }) => call(requestId, () => api.GET("/api/v1/me")));
}

export function listJourneys(): Promise<Result<JourneyPage>> {
  return load(true, "GET /journeys", ({ api, requestId }) =>
    call(requestId, () => api.GET("/api/v1/journeys", { params: { query: { limit: 200 } } })),
  );
}

export function getJourney(journeyId: string): Promise<Result<Journey>> {
  return load(true, "GET /journeys/{id}", ({ api, requestId }) =>
    call(requestId, () => api.GET("/api/v1/journeys/{journey_id}", { params: { path: { journey_id: journeyId } } })),
  );
}

export function getMetrics(journeyId: string): Promise<Result<Metrics>> {
  return load(true, "GET /journeys/{id}/metrics", ({ api, requestId }) =>
    call(requestId, () =>
      api.GET("/api/v1/journeys/{journey_id}/metrics", { params: { path: { journey_id: journeyId } } }),
    ),
  );
}

export function getFriction(journeyId: string): Promise<Result<Friction>> {
  return load(true, "GET /journeys/{id}/friction", ({ api, requestId }) =>
    call(requestId, () =>
      api.GET("/api/v1/journeys/{journey_id}/friction", { params: { path: { journey_id: journeyId } } }),
    ),
  );
}

export function listRuns(status: RunStatus | undefined): Promise<Result<RunSummaryPage>> {
  return load(true, "GET /runs", ({ api, requestId }) =>
    call(requestId, () =>
      api.GET("/api/v1/runs", { params: { query: status ? { status, limit: 50 } : { limit: 50 } } }),
    ),
  );
}

export function getRun(runId: string): Promise<Result<Run>> {
  return load(true, "GET /runs/{id}", ({ api, requestId }) =>
    call(requestId, () => api.GET("/api/v1/runs/{run_id}", { params: { path: { run_id: runId } } })),
  );
}

export function getReport(reportId: string): Promise<Result<Report>> {
  return load(true, "GET /reports/{id}", ({ api, requestId }) =>
    call(requestId, () => api.GET("/api/v1/reports/{report_id}", { params: { path: { report_id: reportId } } })),
  );
}
