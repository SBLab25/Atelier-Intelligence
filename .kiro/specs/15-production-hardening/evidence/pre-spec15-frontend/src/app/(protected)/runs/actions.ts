"use server";

import { redirect } from "next/navigation";

import { fieldError, JOURNEY_ID, optionalInt, problemState, RUN_ID, type ActionState } from "@/lib/action-state";
import { approveRun, resumeRun, startRun, type StartRunRequest } from "@/lib/api/mutations";
import { isKey } from "@/lib/idempotency";
import { requireSession } from "@/lib/session";

/**
 * Run actions (Spec 14, OD-144, OD-145, OD-151). The token never leaves the server; the form only carries the run or
 * journey id and the idempotency key rendered with the page. Success redirects to the run page, which refreshes
 * itself while the run is in progress.
 */
const EXPIRED = "This form is out of date. Reload the page and try again.";

export async function startRunAction(_previous: ActionState<never>, form: FormData): Promise<ActionState<never>> {
  await requireSession();
  const key = form.get("key");
  if (!isKey(key)) {
    return fieldError(EXPIRED);
  }
  const journeyId = String(form.get("journey_id") ?? "").trim();
  if (!JOURNEY_ID.test(journeyId)) {
    return fieldError("Choose a journey.");
  }
  const days = optionalInt(form.get("window_days"), 1, 365);
  const minutes = optionalInt(form.get("window_minutes"), 1, 43200);
  if (days === null) {
    return fieldError("The window in days must be a whole number from 1 to 365.");
  }
  if (minutes === null) {
    return fieldError("The window in minutes must be a whole number from 1 to 43200.");
  }
  if (days !== undefined && minutes !== undefined) {
    return fieldError("Enter a window in days or in minutes, not both.");
  }
  const body: StartRunRequest = {
    journey_id: journeyId,
    auto_approve: form.get("auto_approve") === "on",
    window_days: days ?? null,
    window_minutes: minutes ?? null,
  };
  const result = await startRun(body, key);
  if (!result.ok) {
    return problemState(result.problem);
  }
  redirect(`/runs/${encodeURIComponent(result.data.run_id)}?started=1`);
}

function runIdOf(form: FormData): string | null {
  const runId = String(form.get("run_id") ?? "");
  return RUN_ID.test(runId) ? runId : null;
}

export async function approveRunAction(_previous: ActionState<never>, form: FormData): Promise<ActionState<never>> {
  await requireSession();
  const key = form.get("key");
  const runId = runIdOf(form);
  if (!isKey(key) || runId === null) {
    return fieldError(EXPIRED);
  }
  const result = await approveRun(runId, key);
  if (!result.ok) {
    return problemState(result.problem);
  }
  redirect(`/runs/${encodeURIComponent(runId)}?approved=1`);
}

export async function resumeRunAction(_previous: ActionState<never>, form: FormData): Promise<ActionState<never>> {
  await requireSession();
  const key = form.get("key");
  const runId = runIdOf(form);
  if (!isKey(key) || runId === null) {
    return fieldError(EXPIRED);
  }
  const result = await resumeRun(runId, key);
  if (!result.ok) {
    return problemState(result.problem);
  }
  redirect(`/runs/${encodeURIComponent(runId)}?resumed=1`);
}
