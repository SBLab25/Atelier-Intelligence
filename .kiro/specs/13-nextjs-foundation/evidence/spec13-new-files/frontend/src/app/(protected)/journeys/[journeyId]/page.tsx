import type { Metadata } from "next";
import { Suspense } from "react";

import { ProblemPanel } from "@/components/ProblemPanel";
import { Loading } from "@/components/States";
import { getFriction, getJourney, getMetrics } from "@/lib/api/loaders";
import { FrictionView, JourneyStepsView, MetricsView } from "@/views/journeys";

export const metadata: Metadata = { title: "Journey · CJI" };

async function MetricsRegion({ journeyId }: { readonly journeyId: string }) {
  return <MetricsView result={await getMetrics(journeyId)} />;
}

async function FrictionRegion({ journeyId }: { readonly journeyId: string }) {
  return <FrictionView result={await getFriction(journeyId)} />;
}

export default async function JourneyPage({ params }: { readonly params: Promise<{ journeyId: string }> }) {
  const { journeyId } = await params;
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
  return (
    <>
      <h1>Journey {id}</h1>
      <section className="region" aria-labelledby="steps-heading">
        <h2 id="steps-heading">Steps</h2>
        <JourneyStepsView journey={journey.data} />
      </section>
      <section className="region" aria-labelledby="metrics-heading">
        <h2 id="metrics-heading">Metrics</h2>
        <Suspense fallback={<Loading label="Loading metrics…" />}>
          <MetricsRegion journeyId={id} />
        </Suspense>
      </section>
      <section className="region" aria-labelledby="friction-heading">
        <h2 id="friction-heading">Friction summary</h2>
        <Suspense fallback={<Loading label="Loading friction summary…" />}>
          <FrictionRegion journeyId={id} />
        </Suspense>
      </section>
    </>
  );
}
