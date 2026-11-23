import { NextResponse, type NextRequest } from "next/server";
import { getSession } from "@/lib/session";
import { getRunResults } from "@/lib/api/loaders";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ runId: string }> }
): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  const { runId } = await params;
  if (!runId) {
    return NextResponse.json({ ok: false, error: "Missing runId parameter" }, { status: 400 });
  }

  try {
    const result = await getRunResults(runId);
    if (!result.ok) {
      return NextResponse.json({ ok: false, problem: result.problem }, { status: result.problem.status });
    }
    return NextResponse.json({ ok: true, data: result.data });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
