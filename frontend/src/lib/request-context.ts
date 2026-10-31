import "server-only";

import { headers } from "next/headers";
import { cache } from "react";

import { clientAddress } from "./client-address";

/** Headers for API calls made while serving this request (Spec 15): the trace and the trusted client address. */
export interface EdgeHeaders {
  readonly traceparent: string | null;
  readonly forwardedFor: string | null;
}

const NONE: EdgeHeaders = { traceparent: null, forwardedFor: null };

export const edgeHeaders = cache(async (trustedProxyHops: number): Promise<EdgeHeaders> => {
  let incoming: Headers;
  try {
    incoming = await headers();
  } catch {
    // Outside a request (unit tests, prerendering): no incoming trace or address; the client starts a new trace.
    return NONE;
  }
  return {
    traceparent: incoming.get("traceparent"),
    forwardedFor: clientAddress(incoming.get("x-forwarded-for"), trustedProxyHops),
  };
});
