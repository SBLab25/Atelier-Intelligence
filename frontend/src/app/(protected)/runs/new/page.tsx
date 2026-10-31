import type { Metadata } from "next";

import { ActionForm } from "@/components/ActionForm";
import { ProblemPanel } from "@/components/ProblemPanel";
import { EmptyState } from "@/components/States";
import { listJourneys } from "@/lib/api/loaders";
import { newKey } from "@/lib/idempotency";
import { atLeast, roleHint } from "@/lib/roles";
import { requireSession } from "@/lib/session";

import { startRunAction } from "../actions";

export const metadata: Metadata = { title: "Start a run · CJI" };

/**
 * Start an analysis run (Spec 14, OD-144): the CLI's `cji --run [--auto-approve]` from the browser. The run is driven
 * by the API process; this page only sends the request and then shows the run.
 */
export default async function NewRunPage() {
  const session = await requireSession();
  const journeys = await listJourneys();
  const allowed = atLeast(session.role, "operator");
  return (
    <>
      <h1>Start a run</h1>
      <p>
        A run reads the journey&apos;s events, scores friction, asks the language model for insights and, after
        approval, writes the report. It uses the API&apos;s data mode and analysis services.
      </p>
      {!journeys.ok ? (
        <ProblemPanel problem={journeys.problem} what="Journeys" />
      ) : journeys.data.data.length === 0 ? (
        <EmptyState>No journeys are visible to your token.</EmptyState>
      ) : (
        <ActionForm
          action={startRunAction}
          fields={{ key: newKey() }}
          label="Start run"
          pendingLabel="Starting…"
          what="Start run"
          primary
          disabledReason={allowed ? null : roleHint("operator")}
        >
          <div className="field">
            <label htmlFor="journey_id">Journey</label>
            <select id="journey_id" name="journey_id" defaultValue={journeys.data.data[0]?.journey_id}>
              {journeys.data.data.map((journey) => (
                <option key={journey.journey_id} value={journey.journey_id}>
                  {journey.journey_id} ({journey.mode})
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="window_days">Window in days (demo data, optional, default 30)</label>
            <input id="window_days" name="window_days" type="number" min={1} max={365} inputMode="numeric" />
          </div>
          <div className="field">
            <label htmlFor="window_minutes">Window in minutes (realtime data, optional)</label>
            <input id="window_minutes" name="window_minutes" type="number" min={1} max={43200} inputMode="numeric" />
          </div>
          <div>
            <input id="auto_approve" name="auto_approve" type="checkbox" />
            <label htmlFor="auto_approve">Approve automatically (skip the approval step, like --auto-approve)</label>
          </div>
        </ActionForm>
      )}
    </>
  );
}
