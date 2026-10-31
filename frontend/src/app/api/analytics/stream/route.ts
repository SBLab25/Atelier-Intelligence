import { type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const journeyId = searchParams.get("journey_id") || "all";
  const eventType = searchParams.get("event_type");

  const collectorBase = process.env.CJI_COLLECTOR_URL || "http://127.0.0.1:8000";
  const upstreamUrl = new URL(`${collectorBase}/live/stream`);
  if (journeyId && journeyId !== "all") {
    upstreamUrl.searchParams.set("journey_id", journeyId);
  }
  if (eventType) {
    upstreamUrl.searchParams.set("event_type", eventType);
  }

  try {
    const upstreamRes = await fetch(upstreamUrl.toString(), {
      headers: {
        Accept: "text/event-stream",
      },
      cache: "no-store",
    });

    if (!upstreamRes.ok || !upstreamRes.body) {
      return new Response(
        `event: error\ndata: ${JSON.stringify({ status: "upstream_unavailable", code: upstreamRes.status })}\n\n`,
        {
          status: upstreamRes.status || 502,
          headers: {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache, no-transform",
            Connection: "keep-alive",
          },
        }
      );
    }

    // Pipe upstream SSE byte stream directly to client
    return new Response(upstreamRes.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (err) {
    return new Response(
      `event: error\ndata: ${JSON.stringify({ error: err instanceof Error ? err.message : String(err) })}\n\n`,
      {
        status: 500,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache, no-transform",
          Connection: "keep-alive",
        },
      }
    );
  }
}

