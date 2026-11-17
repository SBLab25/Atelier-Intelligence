import { NextResponse, type NextRequest } from "next/server";
import { proxyReport } from "@/lib/report-proxy";
import { runtimeHtmlReports } from "@/app/api/analytics/route";

/** Report preview: returns the runtime Groq-compiled HTML report if present, or proxies to backend */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> },
): Promise<NextResponse> {
  const { reportId } = await params;

  if (runtimeHtmlReports.has(reportId)) {
    const html = runtimeHtmlReports.get(reportId)!;
    return new NextResponse(html, {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  }

  return proxyReport(request, reportId, "inline");
}
