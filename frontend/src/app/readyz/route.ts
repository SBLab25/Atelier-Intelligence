/**
 * Readiness (Spec 15, OD-168): ready when the configuration is valid and the API reports ready. The answer names
 * no cause; the server log does.
 */
import { ConfigError, parseConfig } from "@/lib/config-core";
import { log } from "@/lib/log";

export const dynamic = "force-dynamic";

function answer(ready: boolean): Response {
  return Response.json(
    { status: ready ? "ready" : "not_ready" },
    { status: ready ? 200 : 503, headers: { "Cache-Control": "no-store" } },
  );
}

export async function GET(): Promise<Response> {
  let config;
  try {
    config = parseConfig(process.env);
  } catch (exc) {
    if (exc instanceof ConfigError) {
      log("error", "readiness: configuration invalid", { problems: exc.problems.length });
      return answer(false);
    }
    throw exc;
  }
  try {
    const response = await fetch(`${config.apiBaseUrl}/api/v1/health/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(Math.min(config.timeoutMs, 3000)),
    });
    if (!response.ok) {
      log("warning", "readiness: api not ready", { status: response.status });
    }
    return answer(response.ok);
  } catch {
    log("warning", "readiness: api unreachable");
    return answer(false);
  }
}
