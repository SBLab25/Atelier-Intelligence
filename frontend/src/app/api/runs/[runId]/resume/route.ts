import { NextResponse, type NextRequest } from "next/server";
import { getSession } from "@/lib/session";
import { resumeRun } from "@/lib/api/mutations";
import { newKey } from "@/lib/idempotency";
import { atLeast } from "@/lib/roles";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> }
): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  if (!atLeast(session.role, "operator")) {
    return NextResponse.json(
      { ok: false, error: "Forbidden: operator role required to resume runs" },
      { status: 403 }
    );
  }

  const { runId } = await params;
  if (!runId) {
    return NextResponse.json({ ok: false, error: "Missing runId parameter" }, { status: 400 });
  }

  try {
    const body = await request.json().catch(() => ({}));
    const key = String(body.key || body.idempotency_key || newKey()).trim();
    const result = await resumeRun(runId, key);

    if (!result.ok) {
      return NextResponse.json({ ok: false, problem: result.problem }, { status: result.problem.status });
    }
    return NextResponse.json({ ok: true, data: result.data }, { status: 202 });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
