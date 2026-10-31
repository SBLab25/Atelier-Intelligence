import type { Metadata } from "next";
import { Suspense } from "react";

import { Loading } from "@/components/States";
import { listJourneys } from "@/lib/api/loaders";
import { JourneyListView } from "@/views/journeys";

export const metadata: Metadata = { title: "Journeys · CJI" };

async function JourneyList() {
  return <JourneyListView result={await listJourneys()} />;
}

export default function JourneysPage() {
  return (
    <>
      <h1>Journeys</h1>
      <Suspense fallback={<Loading label="Loading journeys…" />}>
        <JourneyList />
      </Suspense>
    </>
  );
}
