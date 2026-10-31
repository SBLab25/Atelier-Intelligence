import type { Metadata } from "next";
import { Suspense } from "react";

import { ProblemPanel } from "@/components/ProblemPanel";
import { Loading } from "@/components/States";
import { getFriction, getJourney, getMetrics, type AnalysisWindow } from "@/lib/api/loaders";
import { FrictionView, JourneyStepsView, MetricsView, parseWindow, WindowSelector } from "@/views/journeys";

export const metadata: Metadata = { title: "Journey · CJI" };

async function MetricsRegion({ journeyId, window }: { readonly journeyId: string; readonly window: AnalysisWindow }) {
  return <MetricsView result={await getMetrics(journeyId, window)} />;
}

async function FrictionRegion({ journeyId, window }: { readonly journeyId: string; readonly window: AnalysisWindow }) {
  return <FrictionView result={await getFriction(journeyId, window)} />;
}

export default async function JourneyPage({
  params,
  searchParams,
}: {
  readonly params: Promise<{ journeyId: string }>;
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { journeyId } = await params;
  const query = await searchParams;
  const window = parseWindow(query.days, query.minutes);
  const journey = await getJourney(journeyId);
  if (!journey.ok) {
    return (
      <>
        <h1>Journey</h1>
        <ProblemPanel problem={journey.problem} what="Journey" back={{ href: "/journeys", label: "Back to journeys" }} />
      </>
    );
  }
  const id = journey.data.journey_id;
  const key = `${window.days ?? ""}-${window.minutes ?? ""}`;
  return (
    <>
      <h1>Journey {id}</h1>
      <WindowSelector journey={journey.data} window={window} />
      <section className="region" aria-labelledby="steps-heading">
        <h2 id="steps-heading">Steps</h2>
        <JourneyStepsView journey={journey.data} />
      </section>
      <section className="region" aria-labelledby="metrics-heading">
        <h2 id="metrics-heading">Metrics</h2>
        <Suspense key={`m-${key}`} fallback={<Loading label="Loading metrics…" />}>
          <MetricsRegion journeyId={id} window={window} />
        </Suspense>
      </section>
      <section className="region" aria-labelledby="friction-heading">
        <h2 id="friction-heading">Friction summary</h2>
        <Suspense key={`f-${key}`} fallback={<Loading label="Loading friction summary…" />}>
          <FrictionRegion journeyId={id} window={window} />
        </Suspense>
      </section>
    </>
  );
}
