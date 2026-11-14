import type { NextRequest, NextResponse } from "next/server";

import { proxyReport } from "@/lib/report-proxy";

/** Report download (Spec 14, OD-149): the same document as the preview, sent as an attachment. */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> },
): Promise<NextResponse> {
  const { reportId } = await params;
  return proxyReport(request, reportId, "attachment");
}
