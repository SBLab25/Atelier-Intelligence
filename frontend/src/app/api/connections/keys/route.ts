import { NextResponse, type NextRequest } from "next/server";
import { getSession } from "@/lib/session";
import { listOrProvisionApiKeys, createApiKey, revokeApiKey } from "@/lib/api-keys";

export async function GET(): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  // Multi-tenant isolation: admin sees all keys, individual users see their account keys
  const accountId = session.role === "admin" ? undefined : (session.tokenId || session.label);
  const keys = await listOrProvisionApiKeys(session.journeys, accountId);
  return NextResponse.json({ ok: true, keys });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json().catch(() => ({}));
    const journeyName = String(body.journeyName || body.journey_name || "*").trim();
    const description = String(body.description || `Key for ${journeyName}`).trim();
    const accountId = session.tokenId || session.label;

    const key = await createApiKey({ journeyName, description, accountId });
    return NextResponse.json({ ok: true, key });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: msg }, { status: 400 });
  }
}

export async function DELETE(request: NextRequest): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json().catch(() => ({}));
    const apiKey = String(body.apiKey || body.api_key || "").trim();

    if (!apiKey) {
      return NextResponse.json({ ok: false, error: "apiKey parameter is required" }, { status: 400 });
    }

    const revoked = await revokeApiKey(apiKey);
    return NextResponse.json({ ok: true, revoked });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: msg }, { status: 400 });
  }
}

