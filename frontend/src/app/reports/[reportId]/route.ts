import type { NextRequest, NextResponse } from "next/server";

import { proxyReport } from "@/lib/report-proxy";

/** Report preview (Spec 13, design §5): the API's HTML, sandboxed. Shared code in `lib/report-proxy.ts` (Spec 14). */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> },
): Promise<NextResponse> {
  const { reportId } = await params;
  return proxyReport(request, reportId, "inline");
}
