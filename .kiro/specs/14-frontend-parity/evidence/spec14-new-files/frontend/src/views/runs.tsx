import Link from "next/link";
import type { ReactNode } from "react";

import { ProblemPanel } from "@/components/ProblemPanel";
import { EmptyState, StatusBadge, Timestamp } from "@/components/States";
import { RUN_STATUSES, type Run, type RunStatus, type RunSummaryPage } from "@/lib/api/loaders";
import type { Result } from "@/lib/api/problem";

import { journeyHref } from "./journeys";

export function runHref(runId: string): string {
  return `/runs/${encodeURIComponent(runId)}`;
}

export function reportHref(reportId: string): string {
  return `/reports/${encodeURIComponent(reportId)}`;
}

/** The same report as a file download (Spec 14, OD-149). */
export function downloadHref(reportId: string): string {
  return `/reports/${encodeURIComponent(reportId)}/download`;
}

export function parseStatus(raw: string | string[] | undefined): RunStatus | undefined {
  return typeof raw === "string" && (RUN_STATUSES as readonly string[]).includes(raw) ? (raw as RunStatus) : undefined;
}

/** Status filter: a plain GET form, so it works without JavaScript. */
export function RunFilter({ status }: { readonly status: RunStatus | undefined }) {
  return (
    <form method="get" action="/runs" className="inline-form">
      <div className="field">
        <label htmlFor="status">Status</label>
        <select id="status" name="status" defaultValue={status ?? ""}>
          <option value="">All statuses</option>
          {RUN_STATUSES.map((value) => (
            <option key={value} value={value}>
              {value.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      </div>
      <button type="submit" className="button">
        Filter
      </button>
    </form>
  );
}

export function RunListView({
  result,
  status,
}: {
  readonly result: Result<RunSummaryPage>;
  readonly status: RunStatus | undefined;
}) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Runs" />;
  }
  const runs = result.data.data;
  if (runs.length === 0) {
    return (
      <EmptyState>
        {status ? `No runs with status “${status.replaceAll("_", " ")}”.` : "No runs yet. Start one with cji --run or from Start a run."}
      </EmptyState>
    );
  }
  return (
    <div className="stack">
      <div className="table-wrap">
        <table>
          <caption>Runs, most recently updated first</caption>
          <thead>
            <tr>
              <th scope="col">Run</th>
              <th scope="col">Journey</th>
              <th scope="col">Status</th>
              <th scope="col">Updated</th>
              <th scope="col">Report</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.run_id}>
                <th scope="row">
                  <Link href={runHref(run.run_id)}>
                    <code>{run.run_id}</code>
                  </Link>
                </th>
                <td>
                  <Link href={journeyHref(run.journey_id)}>{run.journey_id}</Link>
                </td>
                <td>
                  <StatusBadge status={run.status} />
                </td>
                <td>
                  <Timestamp value={run.updated_at} />
                </td>
                <td>
                  {run.report_id ? (
                    <a href={reportHref(run.report_id)} target="_blank" rel="noopener noreferrer">
                      Open report<span className="visually-hidden"> for run {run.run_id} (new tab)</span>
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.data.page.next_cursor ? (
        <p className="hint">Showing the latest {result.data.page.limit} runs; older runs are not listed here yet.</p>
      ) : null}
    </div>
  );
}

function yesNo(value: boolean): string {
  return value ? "Yes" : "No";
}

export function RunDetailView({ result, actions }: { readonly result: Result<Run>; readonly actions?: ReactNode }) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Run" back={{ href: "/runs", label: "Back to runs" }} />;
  }
  const run = result.data;
  const steps = Object.entries(run.steps);
  return (
    <div className="stack">
      <dl className="kv">
        <dt>Status</dt>
        <dd>
          <StatusBadge status={run.status} />
        </dd>
        <dt>Journey</dt>
        <dd>
          <Link href={journeyHref(run.journey_id)}>{run.journey_id}</Link>
        </dd>
        <dt>Data mode</dt>
        <dd>{run.mode}</dd>
        <dt>Created</dt>
        <dd>
          <Timestamp value={run.created_at} />
        </dd>
        <dt>Updated</dt>
        <dd>
          <Timestamp value={run.updated_at} />
        </dd>
        <dt>Human approved</dt>
        <dd>{yesNo(run.human_approved)}</dd>
        <dt>Being processed now</dt>
        <dd>{yesNo(run.active)}</dd>
        <dt>Insights</dt>
        <dd>{run.insight_count}</dd>
        <dt>Errors recorded</dt>
        <dd>{run.errors_total}</dd>
        <dt>Report</dt>
        <dd>
          {run.report_id ? (
            <>
              <a href={reportHref(run.report_id)} target="_blank" rel="noopener noreferrer">
                Open report (new tab)
              </a>{" "}
              · <a href={downloadHref(run.report_id)}>Download report</a>
            </>
          ) : (
            "not written yet"
          )}
        </dd>
      </dl>

      {actions}

      <h2>Workflow steps</h2>
      {steps.length === 0 ? (
        <EmptyState>No step has started yet.</EmptyState>
      ) : (
        <div className="table-wrap">
          <table>
            <caption>Workflow steps of this run</caption>
            <thead>
              <tr>
                <th scope="col">Step</th>
                <th scope="col">Status</th>
                <th scope="col">Attempts</th>
                <th scope="col">Started</th>
                <th scope="col">Finished</th>
                <th scope="col">Code</th>
              </tr>
            </thead>
            <tbody>
              {steps.map(([worker, step]) => (
                <tr key={worker}>
                  <th scope="row">{worker}</th>
                  <td>{step.status ? <StatusBadge status={step.status} /> : "—"}</td>
                  <td>{step.attempts ?? "—"}</td>
                  <td>
                    <Timestamp value={step.started_at} />
                  </td>
                  <td>
                    <Timestamp value={step.finished_at} />
                  </td>
                  <td>{step.code ? <code>{step.code}</code> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {run.failure ? (
        <section className="problem" aria-labelledby="failure-heading">
          <h2 id="failure-heading" className="problem-heading">
            Failure in {run.failure.worker}
          </h2>
          <p>{run.failure.message}</p>
          <dl className="problem-facts">
            <dt>Code</dt>
            <dd>
              <code>{run.failure.code}</code>
            </dd>
            <dt>Attempts</dt>
            <dd>{run.failure.attempts}</dd>
            <dt>Retryable</dt>
            <dd>{yesNo(run.failure.retryable)}</dd>
          </dl>
          <p className="hint">
            Resume the run on this page, or with <code>cji --resume --thread-id {run.run_id}</code>.
          </p>
        </section>
      ) : null}
    </div>
  );
}
