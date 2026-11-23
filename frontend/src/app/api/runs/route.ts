import { NextResponse, type NextRequest } from "next/server";
import { getSession } from "@/lib/session";
import { listRuns, type RunStatus, RUN_STATUSES } from "@/lib/api/loaders";
import { startRun } from "@/lib/api/mutations";
import { newKey } from "@/lib/idempotency";
import { atLeast } from "@/lib/roles";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  const searchParams = request.nextUrl.searchParams;
  const statusParam = searchParams.get("status");
  const status: RunStatus | undefined =
    statusParam && (RUN_STATUSES as readonly string[]).includes(statusParam)
      ? (statusParam as RunStatus)
      : undefined;

  try {
    const result = await listRuns(status);
    if (!result.ok) {
      return NextResponse.json({ ok: false, problem: result.problem }, { status: result.problem.status });
    }
    return NextResponse.json({ ok: true, data: result.data });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  if (!atLeast(session.role, "operator")) {
    return NextResponse.json(
      { ok: false, error: "Forbidden: operator role required to start runs" },
      { status: 403 }
    );
  }

  try {
    const body = await request.json().catch(() => ({}));
    const journeyId = String(body.journey_id || body.journeyId || "quest_journey").trim();
    const autoApprove = body.auto_approve !== undefined ? Boolean(body.auto_approve) : true;
    const windowMinutes = body.window_minutes !== undefined && body.window_minutes !== null ? Number(body.window_minutes) : 60;
    const windowDays = body.window_days !== undefined && body.window_days !== null ? Number(body.window_days) : null;
    const idempotencyKey = String(body.idempotency_key || body.idempotencyKey || newKey()).trim();

    const result = await startRun(
      {
        journey_id: journeyId,
        auto_approve: autoApprove,
        window_minutes: windowDays ? null : windowMinutes,
        window_days: windowDays,
      },
      idempotencyKey
    );

    if (!result.ok) {
      return NextResponse.json({ ok: false, problem: result.problem }, { status: result.problem.status });
    }
    return NextResponse.json({ ok: true, data: result.data }, { status: 202 });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
