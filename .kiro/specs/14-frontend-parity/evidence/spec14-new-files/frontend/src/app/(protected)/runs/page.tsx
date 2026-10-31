import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Loading } from "@/components/States";
import { listRuns, type RunStatus } from "@/lib/api/loaders";
import { parseStatus, RunFilter, RunListView } from "@/views/runs";

export const metadata: Metadata = { title: "Runs · CJI" };

async function RunList({ status }: { readonly status: RunStatus | undefined }) {
  return <RunListView result={await listRuns(status)} status={status} />;
}

export default async function RunsPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const status = parseStatus((await searchParams).status);
  return (
    <>
      <h1>Workflow runs</h1>
      <p>
        <Link href="/runs/new" className="button">
          Start a run
        </Link>
      </p>
      <RunFilter status={status} />
      <section className="region" aria-label="Runs">
        <Suspense key={status ?? "all"} fallback={<Loading label="Loading runs…" />}>
          <RunList status={status} />
        </Suspense>
      </section>
    </>
  );
}
