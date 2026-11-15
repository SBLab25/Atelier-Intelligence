import { NextResponse, type NextRequest } from "next/server";
import { getSession } from "@/lib/session";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json();
    const collectorBase = (process.env.CJI_COLLECTOR_URL || "https://atelier-backend-jv2m.onrender.com").replace(/\/$/, "");
    const endpoint = `${collectorBase}/collect/batch`;

    const res = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CJI-Key": body.api_key || "",
      },
      body: JSON.stringify(body),
    });

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: `Collector proxy error: ${msg}` }, { status: 502 });
  }
}
