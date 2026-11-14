import type { Metadata } from "next";
import { Suspense } from "react";

import { Loading } from "@/components/States";
import { listReports } from "@/lib/api/loaders";
import { ReportListView } from "@/views/reports";

export const metadata: Metadata = { title: "Reports · CJI" };

function text(value: string | string[] | undefined, pattern: RegExp): string | undefined {
  return typeof value === "string" && pattern.test(value) ? value : undefined;
}

async function Reports({ journeyId, cursor }: { readonly journeyId: string | undefined; readonly cursor: string | undefined }) {
  return <ReportListView result={await listReports(journeyId, cursor)} journeyId={journeyId} />;
}

export default async function ReportsPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  const journeyId = text(query.journey_id, /^[^\x00-\x1f\x7f/]{1,128}$/);
  const cursor = text(query.cursor, /^[A-Za-z0-9._~-]{1,1024}$/);
  return (
    <>
      <h1>Reports</h1>
      <p>Open a report in a new tab (sandboxed, no scripts) or download it as an HTML file.</p>
      <section className="region" aria-label="Reports">
        <Suspense key={`${journeyId ?? ""}-${cursor ?? ""}`} fallback={<Loading label="Loading reports…" />}>
          <Reports journeyId={journeyId} cursor={cursor} />
        </Suspense>
      </section>
    </>
  );
}
