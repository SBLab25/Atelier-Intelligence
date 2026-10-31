import type { Metadata } from "next";
import { Suspense } from "react";

import { Loading } from "@/components/States";
import { getHealth, getHealthDetails, getMe } from "@/lib/api/loaders";
import { HealthDetailsView, HealthView, MeView } from "@/views/status";

export const metadata: Metadata = { title: "Status · CJI" };

async function HealthRegion() {
  return <HealthView result={await getHealth()} />;
}

async function DetailsRegion() {
  return <HealthDetailsView result={await getHealthDetails()} />;
}

async function MeRegion() {
  return <MeView result={await getMe()} />;
}

export default function StatusPage() {
  return (
    <>
      <h1>Status</h1>
      <section className="region" aria-labelledby="api-heading">
        <h2 id="api-heading">API</h2>
        <Suspense fallback={<Loading label="Loading API health…" />}>
          <HealthRegion />
        </Suspense>
      </section>
      <section className="region" aria-labelledby="components-heading">
        <h2 id="components-heading">Components</h2>
        <Suspense fallback={<Loading label="Loading component status…" />}>
          <DetailsRegion />
        </Suspense>
      </section>
      <section className="region" aria-labelledby="token-heading">
        <h2 id="token-heading">Your token</h2>
        <Suspense fallback={<Loading label="Loading token details…" />}>
          <MeRegion />
        </Suspense>
      </section>
    </>
  );
}
