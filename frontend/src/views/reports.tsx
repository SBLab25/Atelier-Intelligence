import Link from "next/link";

import { Pager } from "@/components/EventsTable";
import { ProblemPanel } from "@/components/ProblemPanel";
import { EmptyState, Timestamp } from "@/components/States";
import type { ReportPage } from "@/lib/api/loaders";
import type { Result } from "@/lib/api/problem";
import { count } from "@/lib/format";

import { downloadHref, reportHref, runHref } from "./runs";

/** Reports, newest first, with preview and download (Spec 14, OD-149); paged with the API's cursor. */
export function ReportListView({
  result,
  journeyId,
}: {
  readonly result: Result<ReportPage>;
  readonly journeyId: string | undefined;
}) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Reports" />;
  }
  const reports = result.data.data;
  if (reports.length === 0) {
    return <EmptyState>No reports yet. A report is written when an approved run finishes.</EmptyState>;
  }
  const next = result.data.page.next_cursor;
  const params = new URLSearchParams();
  if (journeyId) {
    params.set("journey_id", journeyId);
  }
  if (next) {
    params.set("cursor", next);
  }
  return (
    <div className="stack">
      <div className="table-wrap">
        <table>
          <caption>Reports, newest first</caption>
          <thead>
            <tr>
              <th scope="col">Report</th>
              <th scope="col">Journey</th>
              <th scope="col">Run</th>
              <th scope="col">Created</th>
              <th scope="col">Size</th>
              <th scope="col">Download</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((report) => (
              <tr key={report.report_id}>
                <th scope="row">
                  <a href={reportHref(report.report_id)} target="_blank" rel="noopener noreferrer">
                    {report.report_id}
                    <span className="visually-hidden"> (opens in a new tab)</span>
                  </a>
                </th>
                <td>{report.journey_id ?? "—"}</td>
                <td>{report.run_id ? <Link href={runHref(report.run_id)}>{report.run_id}</Link> : "—"}</td>
                <td>
                  <Timestamp value={report.created_at} />
                </td>
                <td>{count(Math.ceil(report.size_bytes / 1024))} KiB</td>
                <td>
                  <a href={downloadHref(report.report_id)}>
                    Download<span className="visually-hidden"> {report.report_id}</span>
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager nextHref={next ? `/reports?${params.toString()}` : null} label="Older reports" />
    </div>
  );
}
