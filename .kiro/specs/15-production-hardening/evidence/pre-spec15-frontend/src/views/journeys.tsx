import Link from "next/link";

import { Bar, MetricsTable } from "@/components/Charts";
import { FrictionSummary } from "@/components/FrictionSummary";
import { ProblemPanel } from "@/components/ProblemPanel";
import { EmptyState } from "@/components/States";
import type { AnalysisWindow, Friction, Journey, JourneyPage, Metrics } from "@/lib/api/loaders";
import { count, pct } from "@/lib/format";
import type { Result } from "@/lib/api/problem";

export function journeyHref(journeyId: string): string {
  return `/journeys/${encodeURIComponent(journeyId)}`;
}

export function JourneyListView({ result }: { readonly result: Result<JourneyPage> }) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Journeys" />;
  }
  const journeys = result.data.data;
  if (journeys.length === 0) {
    return <EmptyState>No journeys are visible to your token.</EmptyState>;
  }
  return (
    <div className="table-wrap">
      <table>
        <caption>Journeys visible to your token</caption>
        <thead>
          <tr>
            <th scope="col">Journey</th>
            <th scope="col">Steps</th>
            <th scope="col">Data mode</th>
          </tr>
        </thead>
        <tbody>
          {journeys.map((journey) => (
            <tr key={journey.journey_id}>
              <th scope="row">
                <Link href={journeyHref(journey.journey_id)}>{journey.journey_id}</Link>
              </th>
              <td>{journey.steps.length}</td>
              <td>{journey.mode}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function JourneyStepsView({ journey }: { readonly journey: Journey }) {
  if (journey.steps.length === 0) {
    return <EmptyState>This journey has no configured steps.</EmptyState>;
  }
  return (
    <ol className="steps">
      {journey.steps.map((step) => (
        <li key={step}>{step}</li>
      ))}
    </ol>
  );
}

export function windowText(metrics: Pick<Metrics, "window">): string {
  if (metrics.window.minutes) {
    return `last ${metrics.window.minutes} minutes`;
  }
  return metrics.window.days ? `last ${metrics.window.days} days` : "all data";
}

export function MetricsView({ result }: { readonly result: Result<Metrics> }) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Journey metrics" />;
  }
  const metrics = result.data;
  const max = Math.max(0, ...metrics.funnel.map((step) => step.users));
  if (metrics.funnel.length === 0 && metrics.steps.length === 0) {
    return <EmptyState>No events in this window ({windowText(metrics)}).</EmptyState>;
  }
  return (
    <div className="stack">
      <p>
        Overall completion: <strong>{pct(metrics.overall_completion_pct)}</strong> ({windowText(metrics)})
      </p>
      <div className="table-wrap">
        <table>
          <caption>Funnel</caption>
          <thead>
            <tr>
              <th scope="col">Step</th>
              <th scope="col">Users</th>
              <th scope="col">Drop-off</th>
            </tr>
          </thead>
          <tbody>
            {metrics.funnel.map((step) => (
              <tr key={step.step_id}>
                <th scope="row">{step.step_id}</th>
                <td>
                  <Bar value={step.users} max={max} />
                  {count(step.users)}
                </td>
                <td>{pct(step.drop_off_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {metrics.steps.length > 0 ? <MetricsTable journeyId={metrics.journey_id} steps={metrics.steps} /> : null}
    </div>
  );
}

export function FrictionView({ result }: { readonly result: Result<Friction> }) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Friction summary" />;
  }
  return <FrictionSummary friction={result.data} />;
}

const DAY_CHOICES = [1, 7, 30, 90, 365] as const;
const MINUTE_CHOICES = [15, 60, 240, 1440] as const;

/** Parse the window of a journey page from its query string; invalid values fall back to the API default. */
export function parseWindow(days: string | string[] | undefined, minutes: string | string[] | undefined): AnalysisWindow {
  const d = typeof days === "string" && /^\d{1,3}$/.test(days) ? Number(days) : undefined;
  const m = typeof minutes === "string" && /^\d{1,5}$/.test(minutes) ? Number(minutes) : undefined;
  if (m !== undefined && m >= 1 && m <= 43200) {
    return { minutes: m };
  }
  if (d !== undefined && d >= 1 && d <= 365) {
    return { days: d };
  }
  return {};
}

/** Window choice as a plain GET form (works without JavaScript); demo data uses days, realtime data minutes. */
export function WindowSelector({ journey, window }: { readonly journey: Journey; readonly window: AnalysisWindow }) {
  const realtime = journey.mode === "realtime";
  const name = realtime ? "minutes" : "days";
  const current = realtime ? (window.minutes ?? 60) : (window.days ?? 30);
  const choices: readonly number[] = realtime ? MINUTE_CHOICES : DAY_CHOICES;
  return (
    <form method="get" className="inline-form">
      <div className="field">
        <label htmlFor="window">Analysis window</label>
        <select id="window" name={name} defaultValue={String(current)}>
          {choices.map((value) => (
            <option key={value} value={value}>
              {realtime ? `last ${value} minutes` : `last ${value} days`}
            </option>
          ))}
        </select>
      </div>
      <button type="submit" className="button">
        Apply
      </button>
    </form>
  );
}
