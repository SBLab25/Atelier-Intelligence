import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { stepHref } from "@/components/Charts";
import { ProblemPanel } from "@/components/ProblemPanel";
import { Loading } from "@/components/States";
import {
  getFriction,
  getInsights,
  getJourney,
  getMetrics,
  listEvents,
  type AnalysisWindow,
} from "@/lib/api/loaders";
import { atLeast } from "@/lib/roles";
import { requireSession } from "@/lib/session";
import { journeyHref, parseWindow } from "@/views/journeys";
import { StepEventsView, StepFrictionView, StepInsightView, StepMetricsView } from "@/views/step-detail";

export const metadata: Metadata = { title: "Step · CJI" };

type Query = Record<string, string | string[] | undefined>;

function text(value: string | string[] | undefined, max: number): string | undefined {
  return typeof value === "string" && value.length > 0 && value.length <= max ? value : undefined;
}

async function Metrics({ journeyId, stepId, window }: { journeyId: string; stepId: string; window: AnalysisWindow }) {
  return <StepMetricsView stepId={stepId} result={await getMetrics(journeyId, window)} />;
}

async function Friction({ journeyId, stepId, window }: { journeyId: string; stepId: string; window: AnalysisWindow }) {
  return <StepFrictionView stepId={stepId} result={await getFriction(journeyId, window)} />;
}

async function Insight({ journeyId, stepId }: { journeyId: string; stepId: string }) {
  return <StepInsightView stepId={stepId} result={await getInsights(journeyId)} />;
}

async function Events({
  journeyId,
  stepId,
  allowed,
  eventType,
  cursor,
}: {
  journeyId: string;
  stepId: string;
  allowed: boolean;
  eventType: string | undefined;
  cursor: string | undefined;
}) {
  const result = allowed ? await listEvents(journeyId, { stepId, eventType, cursor }) : null;
  return (
    <StepEventsView allowed={allowed} result={result} basePath={stepHref(journeyId, stepId)} eventType={eventType} />
  );
}

export default async function StepPage({
  params,
  searchParams,
}: {
  readonly params: Promise<{ journeyId: string; stepId: string }>;
  readonly searchParams: Promise<Query>;
}) {
  const { journeyId, stepId } = await params;
  const query = await searchParams;
  const window = parseWindow(query.days, query.minutes);
  const eventType = text(query.event_type, 64);
  const cursor = text(query.cursor, 1024);
  const session = await requireSession();
  const journey = await getJourney(journeyId);
  if (!journey.ok) {
    return (
      <>
        <h1>Step</h1>
        <ProblemPanel problem={journey.problem} what="Journey" back={{ href: "/journeys", label: "Back to journeys" }} />
      </>
    );
  }
  const id = journey.data.journey_id;
  return (
    <>
      <h1>
        Step {stepId} <span className="hint">in {id}</span>
      </h1>
      <p>
        <Link href={journeyHref(id)}>Back to journey {id}</Link>
      </p>
      {journey.data.steps.includes(stepId) ? null : (
        <p className="notice">This step is not one of the journey&apos;s configured steps.</p>
      )}
      <section className="region" aria-labelledby="step-metrics-heading">
        <h2 id="step-metrics-heading">Metrics</h2>
        <Suspense fallback={<Loading label="Loading step metrics…" />}>
          <Metrics journeyId={id} stepId={stepId} window={window} />
        </Suspense>
      </section>
      <section className="region" aria-labelledby="step-friction-heading">
        <h2 id="step-friction-heading">Friction</h2>
        <Suspense fallback={<Loading label="Loading friction score…" />}>
          <Friction journeyId={id} stepId={stepId} window={window} />
        </Suspense>
      </section>
      <section className="region" aria-labelledby="step-insight-heading">
        <h2 id="step-insight-heading">Latest insight</h2>
        <Suspense fallback={<Loading label="Loading insight…" />}>
          <Insight journeyId={id} stepId={stepId} />
        </Suspense>
      </section>
      <section className="region" aria-labelledby="step-events-heading">
        <h2 id="step-events-heading">Events</h2>
        <Suspense key={`${eventType ?? ""}-${cursor ?? ""}`} fallback={<Loading label="Loading events…" />}>
          <Events
            journeyId={id}
            stepId={stepId}
            allowed={atLeast(session.role, "operator")}
            eventType={eventType}
            cursor={cursor}
          />
        </Suspense>
      </section>
    </>
  );
}
