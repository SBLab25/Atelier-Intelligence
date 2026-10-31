import type { Metadata } from "next";

import { getRun } from "@/lib/api/loaders";
import { RunDetailView } from "@/views/runs";

export const metadata: Metadata = { title: "Run · CJI" };

export default async function RunPage({ params }: { readonly params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const result = await getRun(runId);
  return (
    <>
      <h1>
        Run <code>{runId}</code>
      </h1>
      <RunDetailView result={result} />
    </>
  );
}
