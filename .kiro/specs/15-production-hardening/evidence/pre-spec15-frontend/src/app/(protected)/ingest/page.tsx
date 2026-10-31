import type { Metadata } from "next";

import { IngestFlow } from "@/components/Ingest";
import { atLeast, roleHint } from "@/lib/roles";
import { requireSession } from "@/lib/session";

import { validateAction, writeAction } from "./actions";

export const metadata: Metadata = { title: "Ingest events · CJI" };

/**
 * Event file ingestion with validation feedback (Spec 14, OD-148). Same parser and writer as the Streamlit upload and
 * `cji-ingest-json`; the difference is the review step before anything is written.
 */
export default async function IngestPage() {
  const session = await requireSession();
  return (
    <>
      <h1>Ingest events</h1>
      <p>
        Upload an event file to check what would be stored: rows read, rows skipped, steps and event types found.
        Nothing is written until you confirm. Events go to the <code>tracking_events</code> table that realtime runs and
        the Streamlit dashboard read.
      </p>
      {atLeast(session.role, "operator") ? (
        <IngestFlow validate={validateAction} write={writeAction} canReplace={atLeast(session.role, "admin")} />
      ) : (
        <p className="notice">{roleHint("operator")}</p>
      )}
    </>
  );
}
