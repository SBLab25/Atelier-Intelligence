import Link from "next/link";

import { EventsTable, Pager } from "@/components/EventsTable";
import { ProblemPanel } from "@/components/ProblemPanel";
import { EmptyState } from "@/components/States";
import type { EventPage, Friction, Insights, Metrics } from "@/lib/api/loaders";
import type { Result } from "@/lib/api/problem";
import { count, decimal, pct, seconds } from "@/lib/format";
import { roleHint } from "@/lib/roles";

import { runHref } from "./runs";

/**
 * Friction drill-down for one step (Spec 14, OD-150): its metrics, friction score with signals and confidence, its
 * funnel position, the latest run's insight for the step and its events. Every value is the API's.
 */
export function StepMetricsView({ stepId, result }: { readonly stepId: string; readonly result: Result<Metrics> }) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Step metrics" />;
  }
  const step = result.data.steps.find((s) => s.step_id === stepId);
  const position = result.data.funnel.findIndex((f) => f.step_id === stepId);
  const funnel = position >= 0 ? result.data.funnel[position] : undefined;
  if (!step && !funnel) {
    return <EmptyState>No metrics for this step in the selected window.</EmptyState>;
  }
  return (
    <dl className="kv">
      <dt>Funnel position</dt>
      <dd>{funnel ? `${position + 1} of ${result.data.funnel.length}` : "not in the funnel"}</dd>
      <dt>Users reaching the step</dt>
      <dd>{funnel ? count(funnel.users) : "—"}</dd>
      <dt>Drop-off from the previous step</dt>
      <dd>{funnel ? pct(funnel.drop_off_pct) : "—"}</dd>
      <dt>Unique users</dt>
      <dd>{step ? count(step.unique_users) : "—"}</dd>
      <dt>Completion</dt>
      <dd>{step ? pct(step.completion_rate_pct) : "—"}</dd>
      <dt>Abandon</dt>
      <dd>{step ? pct(step.abandon_rate_pct) : "—"}</dd>
      <dt>Errors</dt>
      <dd>{step ? pct(step.error_rate_pct) : "—"}</dd>
      <dt>Average dwell</dt>
      <dd>{step ? seconds(step.avg_dwell_ms) : "—"}</dd>
      <dt>Rage clicks per user</dt>
      <dd>{step ? decimal(step.avg_rage_clicks) : "—"}</dd>
      <dt>Retries per user</dt>
      <dd>{step ? decimal(step.avg_retries) : "—"}</dd>
    </dl>
  );
}

export function StepFrictionView({ stepId, result }: { readonly stepId: string; readonly result: Result<Friction> }) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Step friction" />;
  }
  const score = result.data.scores.find((s) => s.step_id === stepId);
  if (!score) {
    return <EmptyState>No friction score for this step in the selected window.</EmptyState>;
  }
  return (
    <dl className="kv">
      <dt>Friction score</dt>
      <dd>
        <strong>{score.score}</strong> (critical at {result.data.threshold} or above)
      </dd>
      <dt>Critical</dt>
      <dd>{score.is_critical ? <strong>Yes</strong> : "No"}</dd>
      <dt>Signals</dt>
      <dd>{score.signals.length > 0 ? score.signals.join(", ") : "none"}</dd>
      <dt>Confidence</dt>
      <dd>{score.confidence}</dd>
      <dt>Drop-off rate</dt>
      <dd>{decimal(score.drop_off_rate)}</dd>
      <dt>Average dwell</dt>
      <dd>{seconds(score.avg_dwell_ms)}</dd>
      <dt>Retries per user</dt>
      <dd>{decimal(score.retry_count)}</dd>
      <dt>Rage clicks per user</dt>
      <dd>{decimal(score.rage_click_rate)}</dd>
    </dl>
  );
}

export function StepInsightView({ stepId, result }: { readonly stepId: string; readonly result: Result<Insights> }) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Step insight" />;
  }
  const found = result.data.insights.filter((i) => i.step_id === stepId);
  if (found.length === 0) {
    return (
      <EmptyState>
        {result.data.run_id ? "The latest run with insights has no insight for this step." : "No run has insights yet."}
      </EmptyState>
    );
  }
  return (
    <div className="stack">
      {found.map((insight) => (
        <article key={insight.insight_id} className="insight" aria-labelledby={`step-insight-${insight.insight_id}`}>
          <h3 id={`step-insight-${insight.insight_id}`}>{insight.title}</h3>
          <dl className="kv">
            <dt>Root cause</dt>
            <dd>{insight.root_cause ?? "—"}</dd>
            <dt>Suggested fix</dt>
            <dd>{insight.suggested_fix ?? "—"}</dd>
          </dl>
        </article>
      ))}
      {result.data.run_id ? (
        <p>
          From run <Link href={runHref(result.data.run_id)}>{result.data.run_id}</Link>; its page shows whether the
          language model or a fallback wrote each insight.
        </p>
      ) : null}
    </div>
  );
}

export interface StepEventsProps {
  readonly allowed: boolean;
  readonly result: Result<EventPage> | null;
  readonly basePath: string;
  readonly eventType: string | undefined;
}

export function StepEventsView({ allowed, result, basePath, eventType }: StepEventsProps) {
  if (!allowed || result === null) {
    return <p className="notice">Events are only listed for operators. {roleHint("operator")}</p>;
  }
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Events" />;
  }
  const next = result.data.page.next_cursor;
  const params = new URLSearchParams();
  if (eventType) {
    params.set("event_type", eventType);
  }
  if (next) {
    params.set("cursor", next);
  }
  return (
    <div className="stack">
      <form method="get" action={basePath} className="inline-form">
        <div className="field">
          <label htmlFor="event_type">Event type</label>
          <input id="event_type" name="event_type" type="text" defaultValue={eventType ?? ""} maxLength={64} />
        </div>
        <button type="submit" className="button">
          Filter events
        </button>
      </form>
      <EventsTable page={result.data} caption="Events of this step, newest first" />
      <Pager nextHref={next ? `${basePath}?${params.toString()}` : null} label="Older events" />
    </div>
  );
}
