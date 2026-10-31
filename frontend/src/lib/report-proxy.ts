import "server-only";

import { NextResponse, type NextRequest } from "next/server";

import { localProblem, problemFrom, type Problem } from "./api/problem";
import { clientAddress } from "./client-address";
import { ConfigError, serverConfig } from "./config";
import { log } from "./log";
import { getSession } from "./session";
import { childTraceparent } from "./trace";

/** X-Forwarded-For for the API call when a trusted client address is known (Spec 15). */
function forwarded(address: string | null): Record<string, string> {
  return address ? { "X-Forwarded-For": address } : {};
}

/**
 * Report HTML through the frontend server (Spec 13, design §5; download added in Spec 14, OD-149): the browser never
 * gets the API token. The body is passed through unchanged with the API's restrictive CSP plus `sandbox`, so report
 * content cannot run scripts or reach this origin's cookies. A download keeps the same CSP and adds the API's
 * `Content-Disposition: attachment` header after checking its file name.
 */
const REPORT_ID = /^[A-Za-z0-9_-]{1,140}$/;
const REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox";
const ATTACHMENT = /^attachment; filename="[A-Za-z0-9._-]{1,200}"$/;

export type Disposition = "inline" | "attachment";

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function errorPage(problem: Problem): NextResponse {
  const body = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Report unavailable · CJI</title></head>
<body><main><h1>Report unavailable</h1><p>${escapeHtml(problem.detail || problem.title)}</p>
<p>Status ${problem.status}, code <code>${escapeHtml(problem.code)}</code>${
    problem.requestId ? `, request id <code>${escapeHtml(problem.requestId)}</code>` : ""
  }.</p><p><a href="/reports">Back to reports</a></p></main></body></html>`;
  return new NextResponse(body, {
    status: problem.status >= 400 && problem.status < 600 ? problem.status : 502,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
      "Cache-Control": "no-store",
    },
  });
}

export async function proxyReport(request: NextRequest, reportId: string, disposition: Disposition): Promise<NextResponse> {
  const session = await getSession();
  const self = disposition === "attachment" ? `/reports/${reportId}/download` : `/reports/${reportId}`;
  if (!session) {
    return NextResponse.redirect(new URL(`/login?next=${encodeURIComponent(self)}`, request.url));
  }
  const requestId = crypto.randomUUID();
  if (!REPORT_ID.test(reportId)) {
    return errorPage({
      ...localProblem("unexpected_response", requestId),
      status: 404,
      code: "report_not_found",
      title: "Report not found",
      detail: "No report with this id.",
    });
  }
  let config;
  try {
    config = serverConfig();
  } catch (exc) {
    if (exc instanceof ConfigError) {
      log("error", "configuration invalid", { detail: exc.problems.join("; ") });
      return errorPage(localProblem("service_misconfigured", requestId));
    }
    throw exc;
  }
  const query = disposition === "attachment" ? "?disposition=attachment" : "";
  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl}/api/v1/reports/${encodeURIComponent(reportId)}/content${query}`, {
      headers: {
        Authorization: `Bearer ${session.token}`,
        "X-Request-ID": requestId,
        Accept: "text/html",
        traceparent: childTraceparent(request.headers.get("traceparent")),
        ...forwarded(clientAddress(request.headers.get("x-forwarded-for"), config.trustedProxyHops)),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(config.timeoutMs),
    });
  } catch (exc) {
    const timedOut = exc instanceof DOMException && exc.name === "TimeoutError";
    return errorPage(localProblem(timedOut ? "backend_timeout" : "backend_unreachable", requestId));
  }
  log("info", "api", { call: `GET /reports/{id}/content (${disposition})`, status: response.status, request_id: requestId });
  if (response.status === 401) {
    return NextResponse.redirect(new URL("/auth/expired", request.url), 303);
  }
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    return errorPage(problemFrom(response.status, body, response.headers, requestId));
  }
  const given = response.headers.get("content-disposition") ?? "";
  const contentDisposition =
    disposition === "attachment" ? (ATTACHMENT.test(given) ? given : `attachment; filename="cji_report_${reportId}.html"`) : "inline";
  return new NextResponse(response.body, {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy": REPORT_CSP,
      "Content-Disposition": contentDisposition,
      "X-Content-Type-Options": "nosniff",
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
    },
  });
}
