import type { Metadata } from "next";
import { Suspense } from "react";

import { ActionForm } from "@/components/ActionForm";
import { RunAutoRefresh } from "@/components/RunAutoRefresh";
import { Loading } from "@/components/States";
import { getRun, getRunResults, type Run } from "@/lib/api/loaders";
import { newKey } from "@/lib/idempotency";
import { atLeast, roleHint } from "@/lib/roles";
import type { Role } from "@/lib/session-core";
import { requireSession } from "@/lib/session";
import { RunResultsView } from "@/views/run-results";
import { RunDetailView } from "@/views/runs";

import { approveRunAction, resumeRunAction } from "../actions";

export const metadata: Metadata = { title: "Run · CJI" };

const IN_PROGRESS: ReadonlySet<string> = new Set(["running", "approved"]);
const NOTICES: Readonly<Record<string, string>> = {
  started: "The run was started. Its steps appear below as they finish.",
  approved: "The run was approved. The report step is running.",
  resumed: "The run is resuming from its last stored step.",
};

/** Approve and resume (Spec 14, OD-145, OD-151): shown when the run's status allows them. */
function RunActions({ run, role }: { readonly run: Run; readonly role: Role }) {
  const reason = atLeast(role, "operator") ? null : roleHint("operator");
  const resumable = run.status === "failed" || (IN_PROGRESS.has(run.status) && !run.active);
  if (run.status === "awaiting_approval") {
    return (
      <section className="region" aria-labelledby="approval-heading">
        <h2 id="approval-heading">Approval</h2>
        <p>The analysis is done. Approve the run to write the narrative and the report.</p>
        <ActionForm
          action={approveRunAction}
          fields={{ run_id: run.run_id, key: newKey() }}
          label="Approve run"
          pendingLabel="Approving…"
          what="Approve run"
          primary
          disabledReason={reason}
        />
      </section>
    );
  }
  if (resumable) {
    return (
      <section className="region" aria-labelledby="resume-heading">
        <h2 id="resume-heading">Resume</h2>
        <p>
          {run.status === "failed"
            ? "The run stopped with a failure. Resuming repeats the failed step and continues."
            : "No process is working on this run (for example after an API restart). Resuming continues it."}
        </p>
        <ActionForm
          action={resumeRunAction}
          fields={{ run_id: run.run_id, key: newKey() }}
          label="Resume run"
          pendingLabel="Resuming…"
          what="Resume run"
          disabledReason={reason}
        />
      </section>
    );
  }
  return null;
}

async function Results({ runId }: { readonly runId: string }) {
  return <RunResultsView result={await getRunResults(runId)} />;
}

export default async function RunPage({
  params,
  searchParams,
}: {
  readonly params: Promise<{ runId: string }>;
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { runId } = await params;
  const query = await searchParams;
  const session = await requireSession();
  const result = await getRun(runId);
  const notice = Object.keys(NOTICES).find((name) => query[name] === "1");
  const live = result.ok && (IN_PROGRESS.has(result.data.status) && result.data.active);
  return (
    <>
      <h1>
        Run <code>{runId}</code>
      </h1>
      {notice ? (
        <p className="notice" role="status">
          {NOTICES[notice]}
        </p>
      ) : null}
      {live || (notice && result.ok && result.data.status !== "completed" && result.data.status !== "failed") ? (
        <RunAutoRefresh />
      ) : null}
      <RunDetailView result={result} actions={result.ok ? <RunActions run={result.data} role={session.role} /> : null} />
      {result.ok ? (
        <Suspense fallback={<Loading label="Loading run results…" />}>
          <Results runId={result.data.run_id} />
        </Suspense>
      ) : null}
    </>
  );
}
