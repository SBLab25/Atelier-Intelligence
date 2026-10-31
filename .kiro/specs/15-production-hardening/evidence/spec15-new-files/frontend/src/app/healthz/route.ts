/** Liveness (Spec 15, OD-168): the Next.js server answers. No session, no API call. */
export const dynamic = "force-dynamic";

export function GET(): Response {
  return Response.json({ status: "ok" }, { headers: { "Cache-Control": "no-store" } });
}
