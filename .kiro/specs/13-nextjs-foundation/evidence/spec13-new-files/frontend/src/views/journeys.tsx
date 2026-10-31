import Link from "next/link";

import { FrictionSummary } from "@/components/FrictionSummary";
import { ProblemPanel } from "@/components/ProblemPanel";
import { EmptyState } from "@/components/States";
import type { Friction, Journey, JourneyPage, Metrics } from "@/lib/api/loaders";
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

function windowText(metrics: Pick<Metrics, "window">): string {
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
  if (metrics.funnel.length === 0 && metrics.steps.length === 0) {
    return <EmptyState>No events in this window ({windowText(metrics)}).</EmptyState>;
  }
  return (
    <div className="stack">
      <p>
        Overall completion: <strong>{metrics.overall_completion_pct}%</strong> ({windowText(metrics)})
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
                <td>{step.users}</td>
                <td>{step.drop_off_pct}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function FrictionView({ result }: { readonly result: Result<Friction> }) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Friction summary" />;
  }
  return <FrictionSummary friction={result.data} />;
}
