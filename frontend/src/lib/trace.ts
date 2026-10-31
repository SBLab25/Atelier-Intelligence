/**
 * W3C trace context for calls to the API (Spec 15, OD-161). The request proxy keeps a valid incoming `traceparent`
 * or starts a trace; every API call is a child span of it, so `cji-trace show <trace id>` follows one page request
 * through the API, its runs and the MCP servers. Pure functions.
 */
const TRACEPARENT = /^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$/;

function hex(bytes: number): string {
  const values = crypto.getRandomValues(new Uint8Array(bytes));
  return Array.from(values, (b) => b.toString(16).padStart(2, "0")).join("");
}

export interface TraceContext {
  readonly traceId: string;
  readonly spanId: string;
}

export function parseTraceparent(value: string | null | undefined): TraceContext | null {
  const match = TRACEPARENT.exec((value ?? "").trim().toLowerCase());
  if (!match) {
    return null;
  }
  const [, traceId = "", spanId = ""] = match;
  if (/^0+$/.test(traceId) || /^0+$/.test(spanId)) {
    return null;
  }
  return { traceId, spanId };
}

export function formatTraceparent(context: TraceContext): string {
  return `00-${context.traceId}-${context.spanId}-01`;
}

/** The incoming context, or a new trace. */
export function edgeTrace(incoming: string | null | undefined): TraceContext {
  return parseTraceparent(incoming) ?? { traceId: hex(16), spanId: hex(8) };
}

/** A `traceparent` for one outgoing call: same trace, new span. */
export function childTraceparent(parent: string | null | undefined): string {
  const context = parseTraceparent(parent);
  return formatTraceparent({ traceId: context?.traceId ?? hex(16), spanId: hex(8) });
}
