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
