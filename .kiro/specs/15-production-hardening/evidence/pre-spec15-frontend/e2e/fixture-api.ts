/**
 * Fixture /api/v1 backend for the browser tests (Spec 13, OD-138; extended in Spec 14, design §5). Responses are the
 * typed fixtures of the unit tests, so they follow the OpenAPI schema. It keeps runs in memory and moves them through
 * their statuses on a timer, replays Idempotency-Keys like the API, records every request and can fail chosen calls
 * (fault switches) to drive the error states.
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";

import type { components } from "../src/lib/api/schema";
import * as fx from "../tests/support/fixtures";

type S = components["schemas"];
type Role = S["Me"]["role"];

export const FIXTURE_TOKEN = "cji_api_fixture-token-value-0123456789abcdef";
export const FIXTURE_OPERATOR_TOKEN = "cji_api_fixture-operator-token-0123456789ab";
export const FIXTURE_ADMIN_TOKEN = "cji_api_fixture-admin-token-0123456789abcd";

const TOKENS: Readonly<Record<string, S["Me"]>> = {
  [FIXTURE_TOKEN]: fx.me,
  [FIXTURE_OPERATOR_TOKEN]: fx.operatorMe,
  [FIXTURE_ADMIN_TOKEN]: fx.adminMe,
};
const RANK: Readonly<Record<Role, number>> = { viewer: 0, operator: 1, admin: 2 };

/** How long a fixture run stays in a transient status before it moves on. */
export const STEP_MS = 1500;

export interface RecordedRequest {
  readonly method: string;
  readonly path: string;
  readonly authenticated: boolean;
  readonly requestId: string | null;
  readonly idempotencyKey: string | null;
  readonly contentType: string | null;
  readonly bodyBytes: number;
}

export interface Fault {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly detail: string;
  /** Remaining number of matching requests to fail. */
  count: number;
}

export interface FixtureApi {
  readonly requests: RecordedRequest[];
  failNextFriction(count: number): void;
  /** Fail the next `count` requests whose method and path match (path without query). */
  failNext(method: string, path: string, fault: Omit<Fault, "count">, count?: number): void;
  close(): Promise<void>;
}

const REPORT_HTML = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CJI report</title>
<style>body{font-family:sans-serif}</style></head><body><h1>CJI Report: user_onboarding</h1>
<p>Fixture report for the browser tests.</p></body></html>`;

function send(res: ServerResponse, status: number, body: unknown, type = "application/json", headers: Record<string, string> = {}): void {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  res.writeHead(status, { "Content-Type": type, "Cache-Control": "no-store", ...headers });
  res.end(text);
}

function problem(res: ServerResponse, status: number, code: string, title: string, detail: string, headers: Record<string, string> = {}): void {
  send(res, status, fx.problemBody(status, code, title, detail), "application/problem+json", headers);
}

function readBody(req: IncomingMessage): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function now(): string {
  return new Date().toISOString();
}

function summary(run: S["Run"]): S["RunSummary"] {
  const { run_id, journey_id, mode, status, created_at, updated_at, report_id } = run;
  return { run_id, journey_id, mode, status, created_at, updated_at, report_id };
}

export async function startFixtureApi(port: number): Promise<FixtureApi> {
  const requests: RecordedRequest[] = [];
  const faults: { method: string; path: string; fault: Fault }[] = [];
  const replays = new Map<string, { status: number; body: unknown }>();
  const timers = new Set<NodeJS.Timeout>();
  const runs = new Map<string, S["Run"]>([
    [fx.RUN_ID, fx.run],
    [fx.AWAITING_ID, fx.awaitingRun],
    [fx.FAILED_ID, fx.failedRunToResume],
  ]);
  let created = 0;
  let frictionFailures = 0;

  const later = (fn: () => void) => {
    const timer = setTimeout(() => {
      timers.delete(timer);
      fn();
    }, STEP_MS);
    timers.add(timer);
  };
  const update = (runId: string, patch: Partial<S["Run"]>) => {
    const current = runs.get(runId);
    if (current) {
      runs.set(runId, { ...current, ...patch, updated_at: now() });
    }
  };
  const complete = (runId: string) =>
    update(runId, { status: "completed", active: false, human_approved: true, report_id: fx.REPORT_ID, failure: null });

  const handle = async (req: IncomingMessage, res: ServerResponse) => {
    const url = new URL(req.url ?? "/", "http://fixture");
    const path = url.pathname;
    const method = req.method ?? "GET";
    const token = req.headers.authorization?.replace(/^Bearer /, "") ?? "";
    const me = TOKENS[token];
    const requestId = typeof req.headers["x-request-id"] === "string" ? req.headers["x-request-id"] : null;
    const key = typeof req.headers["idempotency-key"] === "string" ? req.headers["idempotency-key"] : null;
    const body = method === "POST" ? await readBody(req) : Buffer.alloc(0);
    requests.push({
      method, path: path + url.search, authenticated: Boolean(me), requestId, idempotencyKey: key,
      contentType: req.headers["content-type"] ?? null, bodyBytes: body.length,
    });

    if (path === "/api/v1/health") {
      return send(res, 200, fx.health);
    }
    if (!req.headers.authorization?.startsWith("Bearer ")) {
      return problem(res, 401, "missing_token", "Authentication required", "Send 'Authorization: Bearer <token>'.");
    }
    if (!me) {
      return problem(res, 401, "invalid_token", "Invalid token", "The token is unknown, revoked or expired.");
    }
    const fault = faults.find((f) => f.method === method && f.path === path && f.fault.count > 0);
    if (fault) {
      fault.fault.count -= 1;
      const { status, code, title, detail } = fault.fault;
      return problem(res, status, code, title, detail, status === 429 || status === 503 ? { "Retry-After": "2" } : {});
    }
    const needs = (role: Role): boolean => {
      if (RANK[me.role] >= RANK[role]) {
        return true;
      }
      problem(res, 403, "insufficient_role", "Insufficient role", "Your token's role does not allow this request.");
      return false;
    };
    const replayKey = key ? `${token}|${method} ${path}|${key}` : null;
    const replay = replayKey ? replays.get(replayKey) : undefined;
    if (method === "POST" && replay) {
      return send(res, replay.status, replay.body, "application/json", { "Idempotent-Replayed": "true" });
    }
    const answer = (status: number, payload: unknown) => {
      if (replayKey) {
        replays.set(replayKey, { status, body: payload });
      }
      send(res, status, payload);
    };
    if (method === "POST" && !key && path !== "/api/v1/ingestions/validations") {
      return problem(res, 400, "idempotency_key_required", "Idempotency-Key header required", "Send an Idempotency-Key header.");
    }

    const journey = "/api/v1/journeys/user_onboarding";
    const runMatch = /^\/api\/v1\/runs\/([A-Za-z0-9-]+)(\/results|\/approval|\/resume)?$/.exec(path);
    if (runMatch) {
      const [, runId = "", sub] = runMatch;
      const run = runs.get(runId);
      if (!run) {
        return problem(res, 404, "run_not_found", "Run not found", "No run with this id.");
      }
      if (!sub && method === "GET") {
        return send(res, 200, run);
      }
      if (sub === "/results" && method === "GET") {
        const results: S["RunResults"] =
          run.status === "completed"
            ? { ...fx.runResults, run_id: run.run_id, status: run.status }
            : { ...fx.runResults, run_id: run.run_id, status: run.status, narrative: null, prioritized_fixes: [] };
        return send(res, 200, results);
      }
      if (sub === "/approval" && method === "POST") {
        if (!needs("operator")) {
          return;
        }
        if (run.status === "approved" || run.status === "completed") {
          return answer(200, { run, already_approved: true });
        }
        if (run.status !== "awaiting_approval") {
          return problem(res, 409, "run_not_awaiting_approval", "Run is not awaiting approval",
            `The run is ${run.status}; only a run awaiting approval can be approved.`);
        }
        update(runId, { status: "approved", human_approved: true, active: true });
        later(() => complete(runId));
        return answer(202, { run: runs.get(runId), already_approved: false });
      }
      if (sub === "/resume" && method === "POST") {
        if (!needs("operator")) {
          return;
        }
        if (run.status === "completed" || run.status === "awaiting_approval") {
          return problem(res, 409, "run_not_resumable", "Run cannot be resumed", `The run is ${run.status}.`);
        }
        update(runId, { status: "running", active: true, failure: null });
        later(() => complete(runId));
        return answer(202, run);
      }
    }

    switch (`${method} ${path}`) {
      case "GET /api/v1/me":
        return send(res, 200, me);
      case "GET /api/v1/health/details":
        return send(res, 200, fx.healthDetails);
      case "GET /api/v1/journeys":
        return send(res, 200, fx.journeys);
      case `GET ${journey}`:
        return send(res, 200, fx.journey);
      case `GET ${journey}/metrics`:
        return send(res, 200, { ...fx.metrics, window: { days: Number(url.searchParams.get("days") ?? 30), minutes: null } });
      case `GET ${journey}/friction`:
        if (frictionFailures > 0) {
          frictionFailures -= 1;
          return problem(res, 503, "storage_unavailable", "Storage unavailable", "A storage backend is unavailable; retry later.");
        }
        return send(res, 200, fx.friction);
      case `GET ${journey}/insights`:
        return send(res, 200, fx.insights);
      case `GET ${journey}/events`:
        if (!needs("operator")) {
          return;
        }
        return send(res, 200, url.searchParams.get("cursor") ? { ...fx.events, page: { limit: 25, next_cursor: null } } : fx.events);
      case "GET /api/v1/runs":
        return send(res, 200, { data: [...runs.values()].map(summary), page: { limit: 50, next_cursor: null } });
      case "POST /api/v1/runs": {
        if (!needs("operator")) {
          return;
        }
        const request = JSON.parse(body.toString("utf-8") || "{}") as Partial<S["StartRunRequest"]>;
        created += 1;
        const runId = `00000000-0000-4000-8000-${String(created).padStart(12, "0")}`;
        const run: S["Run"] = {
          ...fx.awaitingRun, run_id: runId, journey_id: request.journey_id ?? "user_onboarding", status: "running",
          active: true, steps: {}, created_at: now(), updated_at: now(), human_approved: Boolean(request.auto_approve),
        };
        runs.set(runId, run);
        later(() => (request.auto_approve ? complete(runId) : update(runId, { status: "awaiting_approval", active: false, steps: fx.awaitingRun.steps })));
        return answer(202, run);
      }
      case "GET /api/v1/reports":
        return send(res, 200, fx.reports);
      case `GET /api/v1/reports/${fx.REPORT_ID}/content`: {
        const attachment = url.searchParams.get("disposition") === "attachment";
        return send(res, 200, REPORT_HTML, "text/html; charset=utf-8", {
          "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
          "Content-Disposition": attachment ? `attachment; filename="cji_report_${fx.REPORT_ID}.html"` : "inline",
        });
      }
      case "POST /api/v1/ingestions/validations": {
        if (!needs("operator")) {
          return;
        }
        if (body.length === 0) {
          return problem(res, 422, "ingestion_unreadable", "File not readable", "No records could be read from the file; check its format.");
        }
        return send(res, 201, { ...fx.validation, filename: url.searchParams.get("filename") ?? "upload.json" });
      }
      case "POST /api/v1/ingestions": {
        const request = JSON.parse(body.toString("utf-8") || "{}") as Partial<S["IngestionRequest"]>;
        if (!needs(request.write_mode === "replace" ? "admin" : "operator")) {
          return;
        }
        return answer(201, { ...fx.ingestion, write_mode: request.write_mode ?? "append" });
      }
      default:
        if (path.startsWith("/api/v1/journeys/")) {
          return problem(res, 403, "journey_forbidden", "Journey not allowed", "Your token does not include this journey.");
        }
        return problem(res, 404, "not_found", "Not found", "No such resource.");
    }
  };

  const server: Server = createServer((req, res) => {
    handle(req, res).catch(() => problem(res, 500, "internal_error", "Internal server error", "Fixture failure."));
  });
  await new Promise<void>((resolve) => server.listen(port, "127.0.0.1", resolve));
  return {
    requests,
    failNextFriction(count: number) {
      frictionFailures = count;
    },
    failNext(method: string, path: string, fault: Omit<Fault, "count">, count = 1) {
      faults.push({ method, path, fault: { ...fault, count } });
    },
    close: () =>
      new Promise<void>((resolve) => {
        for (const timer of timers) {
          clearTimeout(timer);
        }
        server.close(() => resolve());
      }),
  };
}
