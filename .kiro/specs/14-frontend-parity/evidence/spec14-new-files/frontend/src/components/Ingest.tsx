"use client";

import { useActionState, useId, useState } from "react";

import { IDLE, type ActionState } from "@/lib/action-state";
import type { Ingestion, IngestionValidation } from "@/lib/api/loaders";
import { count } from "@/lib/format";
import { MAX_UPLOAD_BYTES } from "@/lib/upload";

import { ProblemPanel } from "./ProblemPanel";
import { EmptyState, Timestamp } from "./States";

interface Validated {
  readonly validation: IngestionValidation;
  readonly key: string;
}

export interface IngestFlowProps {
  readonly validate: (previous: ActionState<Validated>, form: FormData) => Promise<ActionState<Validated>>;
  readonly write: (previous: ActionState<Ingestion>, form: FormData) => Promise<ActionState<Ingestion>>;
  readonly canReplace: boolean;
}

/** What validation found (Spec 14, OD-148): counts, steps against the journey, event types and sample rows. */
export function ValidationSummary({ validation }: { readonly validation: IngestionValidation }) {
  const { rows } = validation;
  return (
    <section className="region" aria-labelledby="validation-heading">
      <h2 id="validation-heading">Validation of {validation.filename}</h2>
      <p>
        Nothing has been written yet. Detected format: <strong>{validation.format}</strong>. This validation expires at{" "}
        <Timestamp value={validation.expires_at} />.
      </p>
      <dl className="kv">
        <dt>Rows read from the file</dt>
        <dd>{count(rows.parsed)}</dd>
        <dt>Rows that would be written</dt>
        <dd>{count(rows.accepted)}</dd>
        <dt>Rows skipped (event type outside the CJI taxonomy)</dt>
        <dd>{count(rows.dropped_event_type)}</dd>
        <dt>Rows with an unreadable time (set to the write time)</dt>
        <dd>{count(rows.repaired_timestamp)}</dd>
      </dl>
      {validation.journey_steps_missing.length > 0 ? (
        <p className="notice">
          Journey steps without any row in this file: {validation.journey_steps_missing.join(", ")}.
        </p>
      ) : null}
      <div className="table-wrap">
        <table>
          <caption>Steps found in the file</caption>
          <thead>
            <tr>
              <th scope="col">Step</th>
              <th scope="col">Rows</th>
              <th scope="col">Configured journey step</th>
            </tr>
          </thead>
          <tbody>
            {validation.steps_found.map((step) => (
              <tr key={step.step_id}>
                <th scope="row">{step.step_id}</th>
                <td>{count(step.rows)}</td>
                <td>{step.in_journey ? "Yes" : <strong>No</strong>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="table-wrap">
        <table>
          <caption>Event types found in the file</caption>
          <thead>
            <tr>
              <th scope="col">Event type</th>
              <th scope="col">Rows</th>
            </tr>
          </thead>
          <tbody>
            {validation.event_types.map((type) => (
              <tr key={type.event_type}>
                <th scope="row">{type.event_type}</th>
                <td>{count(type.rows)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {validation.samples.length === 0 ? (
        <EmptyState>No sample rows.</EmptyState>
      ) : (
        <div className="table-wrap">
          <table>
            <caption>First rows as they would be stored (user and session ids hidden)</caption>
            <thead>
              <tr>
                <th scope="col">Step</th>
                <th scope="col">Event type</th>
                <th scope="col">Time</th>
                <th scope="col">Duration (ms)</th>
                <th scope="col">URL</th>
              </tr>
            </thead>
            <tbody>
              {validation.samples.map((row, index) => (
                <tr key={index}>
                  <th scope="row">{row.step_id}</th>
                  <td>{row.event_type}</td>
                  <td>
                    <Timestamp value={row.timestamp} />
                  </td>
                  <td>{row.duration_ms}</td>
                  <td>{row.url || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Refusal({ state, what }: { readonly state: ActionState<unknown>; readonly what: string }) {
  if (state.status !== "error") {
    return null;
  }
  if (state.problem) {
    return <ProblemPanel problem={state.problem} what={what} />;
  }
  return (
    <p className="field-error" role="alert">
      {state.fieldError}
    </p>
  );
}

/**
 * Upload → validation summary → confirm (Spec 14, OD-148). Writing needs the summary of the same file; replacing all
 * stored events needs the admin role and an explicit confirmation.
 */
export function IngestFlow({ validate, write, canReplace }: IngestFlowProps) {
  const [checked, validateAction, validating] = useActionState(validate, IDLE);
  const [written, writeAction, writing] = useActionState(write, IDLE);
  const [mode, setMode] = useState<"append" | "replace">("append");
  const hintId = useId();
  const validation = checked.status === "done" ? checked.data : null;
  const done = written.status === "done" ? written.data : null;
  return (
    <div className="stack">
      <form action={validateAction} className="stack" aria-busy={validating}>
        <div className="field">
          <label htmlFor="file">Event file</label>
          <input id="file" name="file" type="file" accept=".json,.ndjson,.jsonl,.csv" required aria-describedby={hintId} />
          <p id={hintId} className="hint">
            JSON, NDJSON or CSV, at most {MAX_UPLOAD_BYTES / 1048576} MiB. The file is checked first; nothing is written
            until you confirm.
          </p>
        </div>
        <div className="field">
          <label htmlFor="root_key">Root key (optional)</label>
          <input id="root_key" name="root_key" type="text" autoComplete="off" maxLength={64} />
        </div>
        <div className="field">
          <label htmlFor="map">Column mapping (optional, one per line: your_column=cji_column)</label>
          <textarea id="map" name="map" rows={3} />
        </div>
        <div className="actions">
          <button type="submit" className="button button-primary" disabled={validating}>
            {validating ? "Validating…" : "Validate file"}
          </button>
        </div>
        <Refusal state={checked} what="Validate file" />
      </form>

      {validation ? <ValidationSummary validation={validation.validation} /> : null}

      {validation && !done ? (
        <form action={writeAction} className="stack" aria-busy={writing}>
          <input type="hidden" name="validation_id" value={validation.validation.validation_id} />
          <input type="hidden" name="key" value={validation.key} />
          {/* The mode is sent from React state: React resets uncontrolled form fields after an action, which put
              the radio back to "append" while the page still showed "replace" (Spec 14 finding F-82). */}
          <input type="hidden" name="write_mode" value={mode} />
          <fieldset>
            <legend>How to write the validated rows</legend>
            <div>
              <input
                id="mode-append"
                type="radio"
                name="write_mode_choice"
                value="append"
                checked={mode === "append"}
                onChange={() => setMode("append")}
              />
              <label htmlFor="mode-append">Append: add events that are not stored yet</label>
            </div>
            <div>
              <input
                id="mode-replace"
                type="radio"
                name="write_mode_choice"
                value="replace"
                checked={mode === "replace"}
                onChange={() => setMode("replace")}
                disabled={!canReplace}
                aria-describedby={canReplace ? undefined : `${hintId}-replace`}
              />
              <label htmlFor="mode-replace">Replace: delete every stored event, then write this file</label>
              {canReplace ? null : (
                <p id={`${hintId}-replace`} className="hint">
                  Requires the admin role.
                </p>
              )}
            </div>
            {mode === "replace" ? (
              <div>
                <input id="confirm_replace" type="checkbox" name="confirm_replace" />
                <label htmlFor="confirm_replace">I understand that all stored events in tracking_events are deleted.</label>
              </div>
            ) : null}
          </fieldset>
          {validation.validation.database_configured ? null : (
            <p className="notice">No event database is configured for the API, so the file can be validated but not written.</p>
          )}
          <div className="actions">
            <button
              type="submit"
              className="button button-primary"
              disabled={writing || !validation.validation.database_configured || validation.validation.rows.accepted === 0}
            >
              {writing ? "Writing…" : `Write ${count(validation.validation.rows.accepted)} rows`}
            </button>
          </div>
          <Refusal state={written} what="Write events" />
        </form>
      ) : null}

      {done ? (
        <section className="region" aria-labelledby="written-heading">
          <h2 id="written-heading">Events written</h2>
          <p role="status">
            {count(done.rows_written)} rows written to {done.destination} ({done.write_mode}).
            {done.rows_already_stored > 0 ? ` ${count(done.rows_already_stored)} rows were already stored.` : ""} Start a
            run to analyse them.
          </p>
        </section>
      ) : null}
    </div>
  );
}
