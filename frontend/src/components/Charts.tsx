import Link from "next/link";

import type { Metrics } from "@/lib/api/loaders";
import { barWidth, count, decimal, pct, seconds } from "@/lib/format";

/**
 * Funnel bars and the step metrics table (Spec 14, OD-150, OD-152): HTML and CSS only. A bar is decoration next to
 * the number it draws (hidden from screen readers); its length comes from the API's values, nothing is recalculated.
 */
export function Bar({ value, max }: { readonly value: number; readonly max: number }) {
  return (
    <span className="bar-track" aria-hidden="true">
      <span className="bar" style={{ width: `${barWidth(value, max)}%` }} />
    </span>
  );
}

export function stepHref(journeyId: string, stepId: string): string {
  return `/journeys/${encodeURIComponent(journeyId)}/steps/${encodeURIComponent(stepId)}`;
}

export function MetricsTable({ journeyId, steps }: { readonly journeyId: string; readonly steps: Metrics["steps"] }) {
  return (
    <div className="table-wrap">
      <table>
        <caption>Step metrics</caption>
        <thead>
          <tr>
            <th scope="col">Step</th>
            <th scope="col">Unique users</th>
            <th scope="col">Completion</th>
            <th scope="col">Abandon</th>
            <th scope="col">Errors</th>
            <th scope="col">Avg dwell</th>
            <th scope="col">Rage clicks per user</th>
            <th scope="col">Retries per user</th>
          </tr>
        </thead>
        <tbody>
          {steps.map((step) => (
            <tr key={step.step_id}>
              <th scope="row">
                <Link href={stepHref(journeyId, step.step_id)}>{step.step_id}</Link>
              </th>
              <td>{count(step.unique_users)}</td>
              <td>{pct(step.completion_rate_pct)}</td>
              <td>{pct(step.abandon_rate_pct)}</td>
              <td>{pct(step.error_rate_pct)}</td>
              <td>{seconds(step.avg_dwell_ms)}</td>
              <td>{decimal(step.avg_rage_clicks)}</td>
              <td>{decimal(step.avg_retries)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
