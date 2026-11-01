/**
 * API fixtures typed against the generated OpenAPI schema (Spec 13, OD-138): a change in the contract that the
 * frontend depends on fails the type check here. Values follow the demo data shape.
 */
import type { components } from "../../src/lib/api/schema";

type S = components["schemas"];

export const health: S["Health"] = { status: "ok", version: "1.0.0", mode: "demo" };

export const healthDetails: S["HealthDetails"] = {
  status: "degraded",
  version: "1.0.0",
  mode: "demo",
  components: [
    { name: "repository", status: "ok", code: null },
    { name: "checkpoints", status: "ok", code: null },
    { name: "reports", status: "unavailable", code: "storage_unavailable" },
  ],
  active_runs: 0,
};

export const me: S["Me"] = { token_id: "tok_0123456789ab", label: "analyst", role: "viewer", journeys: ["user_onboarding"] };

export const journey: S["Journey"] = {
  journey_id: "user_onboarding",
  steps: ["landing_page", "signup_form", "email_verify", "profile_setup", "payment_info"],
  mode: "demo",
};

export const journeys: S["Page_Journey_"] = { data: [journey], page: { limit: 200, next_cursor: null } };

export const metrics: S["Metrics"] = {
  journey_id: "user_onboarding",
  window: { days: 30, minutes: null },
  steps: [
    {
      step_id: "landing_page",
      unique_users: 2000,
      completion_rate_pct: 91.5,
      abandon_rate_pct: 8.5,
      error_rate_pct: 0.4,
      avg_dwell_ms: 5200,
      avg_rage_clicks: 0.1,
      avg_retries: 0,
    },
  ],
  funnel: [
    { step_id: "landing_page", users: 2000, drop_off_pct: 0 },
    { step_id: "signup_form", users: 1640, drop_off_pct: 18 },
    { step_id: "payment_info", users: 610, drop_off_pct: 62.8 },
  ],
  overall_completion_pct: 30.5,
};

export const friction: S["Friction"] = {
  journey_id: "user_onboarding",
  window: { days: 30, minutes: null },
  threshold: 60,
  scores: [
    {
      step_id: "payment_info",
      score: 78,
      drop_off_rate: 0.63,
      avg_dwell_ms: 41000,
      retry_count: 2.1,
      rage_click_rate: 0.32,
      signals: ["high_drop_off", "rage_clicks"],
      confidence: 0.9,
      is_critical: true,
    },
    {
      step_id: "landing_page",
      score: 12,
      drop_off_rate: 0.08,
      avg_dwell_ms: 5200,
      retry_count: 0,
      rage_click_rate: 0.01,
      signals: [],
      confidence: 0.8,
      is_critical: false,
    },
  ],
  critical_steps: ["payment_info"],
};

export const RUN_ID = "5743856e-4014-4410-942e-eb15cf49851f";
export const REPORT_ID = `user_onboarding_${RUN_ID}`;

export const runs: S["Page_RunSummary_"] = {
  data: [
    {
      run_id: RUN_ID,
      journey_id: "user_onboarding",
      mode: "demo",
      status: "completed",
      created_at: "2026-10-28T21:50:00+00:00",
      updated_at: "2026-10-28T21:52:30+00:00",
      report_id: REPORT_ID,
    },
    {
      run_id: "60a7b337-1da6-4071-9410-cd57fcec01f2",
      journey_id: "user_onboarding",
      mode: "demo",
      status: "awaiting_approval",
      created_at: "2026-10-28T21:55:00+00:00",
      updated_at: "2026-10-28T21:55:20+00:00",
      report_id: null,
    },
  ],
  page: { limit: 50, next_cursor: null },
};

export const run: S["Run"] = {
  run_id: RUN_ID,
  journey_id: "user_onboarding",
  mode: "demo",
  status: "completed",
  created_at: "2026-10-28T21:50:00+00:00",
  updated_at: "2026-10-28T21:52:30+00:00",
  report_id: REPORT_ID,
  human_approved: true,
  active: false,
  steps: {
    data_worker: { status: "done", attempts: 1, started_at: "2026-10-28T21:50:01+00:00", finished_at: "2026-10-28T21:50:05+00:00", code: null },
    report_worker: { status: "done", attempts: 1, started_at: "2026-10-28T21:52:20+00:00", finished_at: "2026-10-28T21:52:30+00:00", code: null },
  },
  failure: null,
  insight_count: 3,
  errors_total: 0,
};

export const failedRun: S["Run"] = {
  ...run,
  status: "failed",
  report_id: null,
  failure: { worker: "data_worker", code: "connect_failed", message: "journey-data server unreachable", retryable: true, attempts: 2 },
};

export function problemBody(status: number, code: string, title: string, detail: string): S["Problem"] {
  return { type: `urn:cji:problem:${code}`, title, status, detail, code, request_id: "req-fixture-0001", errors: null };
}

// -- Spec 14: operators, run results with provenance, events, reports, ingestion -----------------------------

export const operatorMe: S["Me"] = { ...me, token_id: "tok_operator0001", label: "operator", role: "operator" };
export const adminMe: S["Me"] = { ...me, token_id: "tok_admin0000001", label: "admin", role: "admin", journeys: ["*"] };

export const AWAITING_ID = "60a7b337-1da6-4071-9410-cd57fcec01f2";
export const FAILED_ID = "7d1c2a90-5b3e-4f0a-9c1d-2e3f4a5b6c7d";

export const awaitingRun: S["Run"] = {
  ...run,
  run_id: AWAITING_ID,
  status: "awaiting_approval",
  report_id: null,
  human_approved: false,
  steps: {
    data_worker: { status: "succeeded", attempts: 1, started_at: "2026-10-28T21:55:01+00:00", finished_at: "2026-10-28T21:55:05+00:00", code: null },
    insight_worker: { status: "succeeded", attempts: 1, started_at: "2026-10-28T21:55:06+00:00", finished_at: "2026-10-28T21:55:20+00:00", code: null },
  },
};

export const failedRunToResume: S["Run"] = { ...failedRun, run_id: FAILED_ID };

const llm: S["Provenance"] = { source: "llm", model: "openai/gpt-oss-120b", provider: "groq", reason: null, generated_at: "2026-10-28T21:51:00Z" };
const fallback: S["Provenance"] = { source: "fallback", model: null, provider: null, reason: "llm_disabled", generated_at: "2026-10-28T21:51:05Z" };
const notRecorded: S["Provenance"] = { source: "not_recorded", model: null, provider: null, reason: null, generated_at: null };

export const runResults: S["RunResults"] = {
  run_id: RUN_ID,
  journey_id: "user_onboarding",
  status: "completed",
  narrative: "Payment info loses most users; fix the card form first.",
  narrative_provenance: llm,
  friction_scores: friction.scores,
  critical_steps: ["payment_info"],
  insights: [
    {
      insight_id: "ins-payment", step_id: "payment_info", title: "Card form rejects valid input", root_cause: "Strict validation.",
      category: "UX", evidence: ["63% drop-off", "2.1 retries per user"], suggested_fix: "Relax card number validation.",
      fix_effort: "low", priority: 1, priority_score: 98.4, score: 78, provenance: llm,
    },
    {
      insight_id: "ins-signup", step_id: "signup_form", title: "Template insight", root_cause: null, category: "unknown",
      evidence: [], suggested_fix: "Review the step.", fix_effort: "medium", priority: 2, priority_score: 40, score: 61,
      provenance: fallback,
    },
    {
      insight_id: "ins-old", step_id: "landing_page", title: "Older insight", root_cause: null, category: null, evidence: [],
      suggested_fix: null, fix_effort: null, priority: null, priority_score: null, score: null, provenance: notRecorded,
    },
  ],
  prioritized_fixes: [
    { insight_id: "ins-payment", step_id: "payment_info", title: "Card form rejects valid input", suggested_fix: "Relax card number validation.", fix_effort: "low", priority: 1, priority_score: 98.4, category: "UX", root_cause: "Strict validation." },
  ],
  llm_usage: { calls: 3, input_tokens: 1200, output_tokens: 640, cost_usd: 0.0021 },
  ingestion_results: [],
  ingestion_pending_review: [],
  errors: [],
};

export const insights: S["Insights"] = {
  journey_id: "user_onboarding",
  run_id: RUN_ID,
  insights: runResults.insights.map(({ provenance, ...rest }) => {
    void provenance; // GET /journeys/{id}/insights has no provenance field
    return rest;
  }),
};

export const events: S["Page_Event_"] = {
  data: [
    { event_id: "e-1", user_id: "u-1", session_id: "s-1", step_id: "payment_info", event_type: "error", timestamp: "2026-10-28T20:00:00.000000Z", duration_ms: 1200, url: "/pay" },
    { event_id: "e-2", user_id: "u-2", session_id: "s-2", step_id: "payment_info", event_type: "abandon", timestamp: "2026-10-28T19:59:00.000000Z", duration_ms: null, url: null },
  ],
  page: { limit: 25, next_cursor: "eyJrIjpbXX0.c2lnbmF0dXJlMDEyMzQ1Njc4OQ" },
};

export const report: S["Report"] = {
  report_id: REPORT_ID, run_id: RUN_ID, journey_id: "user_onboarding", size_bytes: 20480,
  created_at: "2026-10-28T21:52:30Z", content_url: `/api/v1/reports/${REPORT_ID}/content`,
};

export const reports: S["Page_Report_"] = { data: [report], page: { limit: 25, next_cursor: null } };

export const validation: S["IngestionValidation"] = {
  validation_id: "AbCdEfGhIjKlMnOpQrStUvWx",
  filename: "events.json",
  format: "JSON array",
  rows: { parsed: 4, accepted: 3, dropped_event_type: 1, repaired_timestamp: 1 },
  steps_found: [
    { step_id: "landing_page", rows: 2, in_journey: true },
    { step_id: "unknown_step", rows: 1, in_journey: false },
  ],
  journey_steps_missing: ["payment_info"],
  event_types: [{ event_type: "page_view", rows: 2 }, { event_type: "error", rows: 1 }],
  samples: [{ step_id: "landing_page", event_type: "page_view", timestamp: "2026-01-01T10:00:00Z", duration_ms: 1200, url: "/" }],
  database_configured: true,
  expires_at: "2026-10-28T23:00:00Z",
};

export const ingestion: S["Ingestion"] = {
  validation_id: validation.validation_id, write_mode: "append", rows_written: 3, rows_already_stored: 0,
  destination: "tracking_events",
};
