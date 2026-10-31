/**
 * Fixture /api/v1 backend for the smoke test (Spec 13, OD-138). Responses are the typed fixtures of the unit tests,
 * so they follow the OpenAPI schema. It records every request and can fail the next friction call (fault switch).
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";

import * as fx from "../tests/support/fixtures";

export const FIXTURE_TOKEN = "cji_api_fixture-token-value-0123456789abcdef";

export interface RecordedRequest {
  readonly path: string;
  readonly authenticated: boolean;
  readonly requestId: string | null;
}

export interface FixtureApi {
  readonly requests: RecordedRequest[];
  failNextFriction(count: number): void;
  close(): Promise<void>;
}

const REPORT_HTML = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CJI report</title>
<style>body{font-family:sans-serif}</style></head><body><h1>CJI Report — user_onboarding</h1>
<p>Fixture report for the smoke test.</p></body></html>`;

function send(res: ServerResponse, status: number, body: unknown, type = "application/json"): void {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  res.writeHead(status, { "Content-Type": type, "Cache-Control": "no-store" });
  res.end(text);
}

function problem(res: ServerResponse, status: number, code: string, title: string, detail: string): void {
  send(res, status, fx.problemBody(status, code, title, detail), "application/problem+json");
}

export async function startFixtureApi(port: number): Promise<FixtureApi> {
  const requests: RecordedRequest[] = [];
  let frictionFailures = 0;

  const handler = (req: IncomingMessage, res: ServerResponse) => {
    const url = new URL(req.url ?? "/", "http://fixture");
    const path = url.pathname;
    const authenticated = req.headers.authorization === `Bearer ${FIXTURE_TOKEN}`;
    const requestId = typeof req.headers["x-request-id"] === "string" ? req.headers["x-request-id"] : null;
    requests.push({ path: path + url.search, authenticated, requestId });

    if (path === "/api/v1/health") {
      return send(res, 200, fx.health);
    }
    if (!req.headers.authorization?.startsWith("Bearer ")) {
      return problem(res, 401, "missing_token", "Authentication required", "Send 'Authorization: Bearer <token>'.");
    }
    if (!authenticated) {
      return problem(res, 401, "invalid_token", "Invalid token", "The token is unknown, revoked or expired.");
    }
    const journey = "/api/v1/journeys/user_onboarding";
    switch (path) {
      case "/api/v1/me":
        return send(res, 200, fx.me);
      case "/api/v1/health/details":
        return send(res, 200, fx.healthDetails);
      case "/api/v1/journeys":
        return send(res, 200, fx.journeys);
      case journey:
        return send(res, 200, fx.journey);
      case `${journey}/metrics`:
        return send(res, 200, fx.metrics);
      case `${journey}/friction`:
        if (frictionFailures > 0) {
          frictionFailures -= 1;
          return problem(res, 503, "storage_unavailable", "Storage unavailable", "A storage backend is unavailable; retry later.");
        }
        return send(res, 200, fx.friction);
      case "/api/v1/runs":
        return send(res, 200, fx.runs);
      case `/api/v1/runs/${fx.RUN_ID}`:
        return send(res, 200, fx.run);
      case `/api/v1/reports/${fx.REPORT_ID}/content`:
        return send(res, 200, REPORT_HTML, "text/html; charset=utf-8");
      default:
        if (path.startsWith("/api/v1/journeys/")) {
          return problem(res, 403, "journey_forbidden", "Journey not allowed", "Your token does not include this journey.");
        }
        return problem(res, 404, "not_found", "Not found", "No such resource.");
    }
  };

  const server: Server = createServer(handler);
  await new Promise<void>((resolve) => server.listen(port, "127.0.0.1", resolve));
  return {
    requests,
    failNextFriction(count: number) {
      frictionFailures = count;
    },
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}
