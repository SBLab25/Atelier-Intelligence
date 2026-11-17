import { NextResponse, type NextRequest } from "next/server";
import { getDbPool } from "@/lib/supabase-auth";
import { startRun } from "@/lib/api/loaders";

export type AnalyticsTable = "veriscape_trial_events" | "live_events" | "tracking_events" | "all";

export interface CompiledReportItem {
  report_id: string;
  run_id: string | null;
  journey_id: string | null;
  table: AnalyticsTable;
  window_label: string;
  size_bytes: number;
  created_at: string;
  content_url: string;
  narrative?: string | undefined;
  insights?: LiveTelemetryPayload["insights"] | undefined;
  summary?: {
    totalSessions: number;
    totalEvents: number;
    completionPct: number;
    avgFriction: number;
    criticalCount: number;
    topBottleneck: string;
  } | undefined;
}

export interface LiveTelemetryPayload {
  journeyId: string;
  selectedTable: AnalyticsTable;
  windowMinutes: number;
  windowLabel: string;
  totalEventsInWindow: number;
  mode: "realtime" | "demo";
  isLiveSupabase: boolean;
  status: "connected" | "fallback" | "error";
  statusMessage: string;
  metrics: {
    overallCompletionPct: number;
    funnel: Array<{ step_id: string; users: number; drop_off_pct: number }>;
    steps: Array<{
      step_id: string;
      unique_users: number;
      completion_rate_pct: number;
      abandon_rate_pct: number;
      error_rate_pct: number;
      avg_dwell_ms: number;
      avg_rage_clicks: number;
      avg_retries: number;
    }>;
  } | null;
  friction: {
    threshold: number;
    overallScore: number;
    criticalSteps: string[];
    scores: Array<{
      step_id: string;
      score: number;
      is_critical: boolean;
      signals: string[];
      confidence: string;
    }>;
  } | null;
  events: Array<{
    event_id: string;
    timestamp: string;
    user_id: string | null;
    session_id: string | null;
    step_id: string | null;
    event_type: string | null;
    duration_ms: number | null;
    url: string | null;
  }>;
  insights: Array<{
    id: string;
    title: string;
    description: string;
    severity: "critical" | "urgent" | "minor";
    confidence: number;
    recommendation: string;
    detectedAt: string;
  }>;
  reports?: CompiledReportItem[];
  narrative?: string | undefined;
  availableJourneys: string[];
  lastUpdated: string;
}

export const runtimeHtmlReports = new Map<string, string>();

// Cache Groq insights per (table|journey|minutes|eventCount) for 3 minutes to keep filter switching snappy
const groqCache = new Map<
  string,
  { expiresAt: number; result: { insights: LiveTelemetryPayload["insights"]; narrative?: string | undefined } }
>();

// Scoped in-memory compiled reports per (table|journey) so reports change when switching tables/windows
const scopedCompiledReports = new Map<string, CompiledReportItem[]>();

interface CustomLlmConfig {
  provider?: string | undefined;
  apiKey?: string | undefined;
  model?: string | undefined;
  baseUrl?: string | undefined;
}

interface GroqResponsePayload {
  insights?: Array<{
    id?: string;
    title?: string;
    description?: string;
    severity?: "critical" | "urgent" | "minor";
    confidence?: number;
    recommendation?: string;
  }>;
  narrative?: string;
}

const CANONICAL_JOURNEY_STEPS: Record<string, string[]> = {
  quest_journey: [
    "home",
    "auth",
    "all-quests",
    "quest-detail",
    "quest-map",
    "submit-quest",
    "quest-chains",
    "leaderboard",
  ],
  seasonal_events_flow: [
    "home",
    "seasonal-events",
    "ar-explorer",
    "treasure",
    "badge-gallery",
  ],
  user_onboarding: [
    "landing_page",
    "sign_up_form",
    "email_verification",
    "profile_setup",
    "plan_selection",
    "payment_info",
    "confirm_details",
    "onboarding_done",
  ],
  onboarding: [
    "landing_page",
    "sign_up_form",
    "email_verification",
    "profile_setup",
    "plan_selection",
    "payment_info",
    "confirm_details",
    "onboarding_done",
  ],
};

function normalizeTable(raw: string | null | undefined): AnalyticsTable {
  if (raw === "veriscape_trial_events") return "veriscape_trial_events";
  if (raw === "live_events") return "live_events";
  if (raw === "tracking_events") return "tracking_events";
  if (raw === "all") return "all";
  return "veriscape_trial_events";
}

function formatWindowLabel(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes <= 0 || minutes >= 525600) return "All";
  if (minutes < 60) return `${minutes}m`;
  if (minutes === 60) return "1h";
  if (minutes < 1440) return `${Math.round(minutes / 60)}h`;
  if (minutes === 1440) return "24h";
  return `${Math.round(minutes / 1440)}d`;
}

function tableSourceSql(table: AnalyticsTable): string {
  const veriscapeSql = `
    SELECT
      event_id::text AS event_id,
      user_id::text AS user_id,
      session_id::text AS session_id,
      journey_name::text AS journey_id,
      step_id::text AS step_id,
      event_type::text AS event_type,
      (timestamp AT TIME ZONE 'UTC') AS ts_utc,
      COALESCE(duration_ms, 0)::integer AS duration_ms,
      url::text AS url,
      metadata::text AS metadata
    FROM veriscape_trial_events
  `;
  const liveSql = `
    SELECT
      event_id::text AS event_id,
      user_id::text AS user_id,
      session_id::text AS session_id,
      journey_name::text AS journey_id,
      step_id::text AS step_id,
      event_type::text AS event_type,
      (timestamp AT TIME ZONE 'UTC') AS ts_utc,
      COALESCE(CAST(NULLIF(metadata->>'duration_ms', '') AS INTEGER), 0)::integer AS duration_ms,
      url::text AS url,
      metadata::text AS metadata
    FROM live_events
  `;
  const trackingSql = `
    SELECT
      event_id::text AS event_id,
      user_id::text AS user_id,
      session_id::text AS session_id,
      journey_id::text AS journey_id,
      step_id::text AS step_id,
      event_type::text AS event_type,
      timestamp::timestamptz AS ts_utc,
      COALESCE(duration_ms, 0)::integer AS duration_ms,
      url::text AS url,
      metadata::text AS metadata
    FROM tracking_events
  `;

  if (table === "veriscape_trial_events") return veriscapeSql;
  if (table === "live_events") return liveSql;
  if (table === "tracking_events") return trackingSql;
  return `${veriscapeSql} UNION ALL ${liveSql} UNION ALL ${trackingSql}`;
}

async function generateGroqInsights(
  apiKey: string,
  model: string,
  journeyId: string,
  table: AnalyticsTable,
  windowLabel: string,
  totalEvents: number,
  funnel: Array<{ step_id: string; users: number; drop_off_pct: number }>,
  steps: NonNullable<LiveTelemetryPayload["metrics"]>["steps"],
  friction: NonNullable<LiveTelemetryPayload["friction"]>,
  completionPct: number
): Promise<{ insights: LiveTelemetryPayload["insights"]; narrative?: string | undefined } | null> {
  const cleanKey = apiKey.trim();
  if (!cleanKey || funnel.length === 0) return null;

  let resolvedModel = model?.trim() || process.env.GROQ_MODEL?.trim() || process.env.LLM_MODEL?.trim() || "openai/gpt-oss-120b";
  const url = "https://api.groq.com/openai/v1/chat/completions";

  const systemPrompt = `You are CJI Strategic Machine Intelligence, an expert AI customer journey telemetry analyst powered by Groq.
Analyze the EXACT Supabase table, journey, time window, funnel metrics, and friction vectors provided.
Every title, description, recommendation, and executive narrative MUST reference the actual step names, numbers, table name, and time window from the input data. Do not invent step names that are not in the input.
Respond ONLY with a valid JSON object matching this exact schema:
{
  "insights": [
    {
      "id": "ins-groq-1",
      "title": "Short title describing root cause (max 10 words)",
      "description": "2-3 sentences citing exact numbers and step names from the telemetry",
      "severity": "critical" | "urgent" | "minor",
      "confidence": 95,
      "recommendation": "1-2 sentences of actionable engineering or UX remediation specific to that step"
    }
  ],
  "narrative": "A crisp 2-paragraph executive summary evaluating this specific table, journey, and time window, highlighting primary friction cliffs and expected recovery impact."
}
Return 3 to 4 distinct insights ordered from highest to lowest severity.`;

  const userPrompt = JSON.stringify(
    {
      supabase_table: table,
      journey_name: journeyId,
      time_window: windowLabel,
      total_events_in_window: totalEvents,
      overall_funnel_completion_pct: completionPct,
      overall_friction_score: friction.overallScore,
      critical_steps: friction.criticalSteps,
      funnel_steps: funnel.slice(0, 10),
      step_telemetry: steps.slice(0, 10),
      friction_scores: friction.scores.slice(0, 10),
    },
    null,
    2
  );

  const callGroq = async (modelToUse: string) => {
    return await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${cleanKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: modelToUse,
        messages: [
          { role: "system", content: systemPrompt },
          {
            role: "user",
            content: `Analyze this customer journey dataset for table [${table}], journey [${journeyId}], window [${windowLabel}]:\n\n${userPrompt}`,
          },
        ],
        temperature: 0.2,
        response_format: { type: "json_object" },
      }),
    });
  };

  try {
    let res = await callGroq(resolvedModel);
    if (!res.ok && res.status === 404 && resolvedModel !== "openai/gpt-oss-120b") {
      resolvedModel = "openai/gpt-oss-120b";
      res = await callGroq(resolvedModel);
    }

    if (!res.ok) {
      const errText = await res.text().catch(() => "");
      console.warn(`Groq API returned error status ${res.status}:`, errText);
      return null;
    }

    const data = await res.json();
    const content = data?.choices?.[0]?.message?.content;
    if (!content) return null;

    const parsed: GroqResponsePayload = JSON.parse(content);
    const rawInsights = Array.isArray(parsed.insights) ? parsed.insights : [];
    const formattedInsights: LiveTelemetryPayload["insights"] = rawInsights.map((ins, idx) => ({
      id: ins.id || `ins-groq-${table}-${windowLabel}-${idx + 1}-${Date.now().toString(36)}`,
      title: String(ins.title || "Strategic Machine Insight"),
      description: String(ins.description || "Identified behavioral bottleneck in telemetry stream."),
      severity:
        ins.severity === "critical" || ins.severity === "urgent" || ins.severity === "minor"
          ? ins.severity
          : "urgent",
      confidence: typeof ins.confidence === "number" ? Math.min(99, Math.max(70, Math.round(ins.confidence))) : 94,
      recommendation: String(ins.recommendation || "Review and optimize step flow."),
      detectedAt: `Groq (${resolvedModel})`,
    }));

    return {
      insights: formattedInsights,
      narrative: typeof parsed.narrative === "string" ? parsed.narrative : undefined,
    };
  } catch (err) {
    console.warn("Groq inference error:", err);
    return null;
  }
}

function escapeHtml(val: string): string {
  return val.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function buildReportHtml(
  reportId: string,
  journeyId: string,
  table: AnalyticsTable,
  windowLabel: string,
  totalEvents: number,
  narrative: string,
  insights: LiveTelemetryPayload["insights"],
  funnel: Array<{ step_id: string; users: number; drop_off_pct: number }>,
  friction: NonNullable<LiveTelemetryPayload["friction"]>,
  completionPct: number
): string {
  const safeJourney = escapeHtml(journeyId);
  const safeTable = escapeHtml(table);
  const safeWindow = escapeHtml(windowLabel);
  const safeNarrative = escapeHtml(narrative);

  const funnelRowsHtml = funnel
    .map((step, idx) => {
      const fScore = friction.scores.find((f) => f.step_id === step.step_id);
      const score = fScore?.score ?? 0;
      const sigs = fScore?.signals?.join(", ") || "none";
      const isCrit = score >= 35 || step.drop_off_pct >= 30;
      return `
        <tr>
          <td style="padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.08);">${idx + 1}. ${escapeHtml(step.step_id)}</td>
          <td style="padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.08); font-family: monospace;">${step.users.toLocaleString()}</td>
          <td style="padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.08); font-family: monospace; color: ${step.drop_off_pct >= 25 ? "#f87171" : "#e4e4e7"};">${step.drop_off_pct.toFixed(1)}%</td>
          <td style="padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.08); font-family: monospace; font-weight: 700; color: ${isCrit ? "#f87171" : "#34d399"};">${score}/100</td>
          <td style="padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.08); font-family: monospace; font-size: 11px; color: #a1a1aa;">${escapeHtml(sigs)}</td>
        </tr>
      `;
    })
    .join("");

  const insightsHtml = insights
    .map(
      (ins) => `
    <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 16px; margin-bottom: 12px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <span style="font-size: 11px; color: #a1a1aa; font-family: monospace;">${escapeHtml(ins.detectedAt || "Telemetry Engine")}</span>
        <span style="font-size: 10px; font-weight: 700; text-transform: uppercase; padding: 2px 8px; border-radius: 9999px; ${ins.severity === "critical" ? "background: rgba(239,68,68,0.2); color: #f87171;" : ins.severity === "urgent" ? "background: rgba(245,158,11,0.2); color: #fbbf24;" : "background: rgba(16,185,129,0.2); color: #34d399;"}">${escapeHtml(ins.severity)}</span>
      </div>
      <h3 style="margin: 0 0 6px 0; font-size: 16px; color: #f4f4f5;">${escapeHtml(ins.title)}</h3>
      <p style="margin: 0 0 10px 0; font-size: 13px; color: #d4d4d8; line-height: 1.5;">${escapeHtml(ins.description)}</p>
      <div style="background: rgba(99,102,241,0.1); border-left: 3px solid #6366f1; padding: 8px 12px; font-size: 12px; color: #c7d2fe;">
        <strong>Recommendation:</strong> ${escapeHtml(ins.recommendation)}
      </div>
    </div>
  `
    )
    .join("");

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CJI Executive Report · ${safeTable} · ${safeJourney} (${safeWindow})</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #09090b; color: #f4f4f5; margin: 0; padding: 32px 20px; }
    .container { max-width: 960px; margin: 0 auto; }
    .header { border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 20px; margin-bottom: 24px; }
    .badge { display: inline-block; padding: 3px 10px; font-size: 11px; font-weight: 600; border-radius: 9999px; background: rgba(99,102,241,0.2); color: #818cf8; margin-bottom: 12px; }
    h1 { margin: 0 0 6px 0; font-size: 26px; }
    .narrative-box { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; margin-bottom: 28px; line-height: 1.65; font-size: 14px; color: #e4e4e7; }
    .section-title { font-size: 18px; margin: 24px 0 12px 0; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 8px; }
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 24px; }
    .stat-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 14px; text-align: center; }
    .stat-val { font-size: 22px; font-weight: 700; color: #818cf8; }
    .stat-lbl { font-size: 11px; color: #a1a1aa; text-transform: uppercase; margin-top: 4px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; background: rgba(255,255,255,0.02); border-radius: 8px; overflow: hidden; }
    th { text-align: left; padding: 10px 12px; background: rgba(255,255,255,0.06); color: #a1a1aa; font-size: 11px; text-transform: uppercase; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="badge">CJI Strategic Machine Intelligence · Table: ${safeTable} · Window: ${safeWindow}</div>
      <h1>Customer Journey Intelligence Report: ${safeJourney}</h1>
      <p style="color: #a1a1aa; font-size: 13px; margin: 4px 0 0 0;">Report ID: <code>${escapeHtml(reportId)}</code> · Events Analyzed: <strong>${totalEvents.toLocaleString()}</strong> · Generated: ${new Date().toUTCString()}</p>
    </div>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-val">${completionPct.toFixed(1)}%</div>
        <div class="stat-lbl">Funnel Conversion</div>
      </div>
      <div class="stat-card">
        <div class="stat-val">${(funnel[0]?.users ?? 0).toLocaleString()}</div>
        <div class="stat-lbl">Entrant Sessions</div>
      </div>
      <div class="stat-card">
        <div class="stat-val">${friction.overallScore}/100</div>
        <div class="stat-lbl">Avg Friction Score</div>
      </div>
      <div class="stat-card">
        <div class="stat-val">${friction.criticalSteps.length}</div>
        <div class="stat-lbl">Critical Bottlenecks</div>
      </div>
      <div class="stat-card">
        <div class="stat-val">${totalEvents.toLocaleString()}</div>
        <div class="stat-lbl">Events (${safeWindow})</div>
      </div>
    </div>

    <h2 class="section-title">Executive Summary</h2>
    <div class="narrative-box">
      <p style="margin: 0;">${safeNarrative.replace(/\n\n+/g, "</p><p style='margin-top:12px;'>")}</p>
    </div>

    <h2 class="section-title">Stage Funnel &amp; Friction Matrix</h2>
    <table>
      <thead>
        <tr>
          <th>Stage</th>
          <th>Users</th>
          <th>Drop-off %</th>
          <th>Friction</th>
          <th>Signals</th>
        </tr>
      </thead>
      <tbody>
        ${funnelRowsHtml || `<tr><td colspan="5" style="padding: 16px; text-align: center; color: #a1a1aa;">No stage events recorded in this time window.</td></tr>`}
      </tbody>
    </table>

    <h2 class="section-title">Strategic Insights &amp; Action Items</h2>
    ${insightsHtml}
  </div>
</body>
</html>`;
}

async function querySupabaseAnalytics(
  table: AnalyticsTable,
  requestedJourney: string | null,
  minutes: number
) {
  const pool = getDbPool();
  const srcSql = tableSourceSql(table);
  const isAllTime = !Number.isFinite(minutes) || minutes <= 0 || minutes >= 525600;

  // 1. Discover real journeys present in this table
  const journeysRes = await pool.query<{ journey_id: string; cnt: string }>(`
    WITH src AS (${srcSql})
    SELECT journey_id, COUNT(*)::text AS cnt
    FROM src
    WHERE journey_id IS NOT NULL AND journey_id <> ''
    GROUP BY journey_id
    ORDER BY COUNT(*) DESC
    LIMIT 20
  `);

  const discovered = journeysRes.rows.map((r) => r.journey_id);
  const availableJourneys = discovered.length > 0 ? [...discovered, "all"] : ["all"];

  // If the requested journey does not exist in this table, switch cleanly to the top journey in this table
  const effectiveJourney =
    requestedJourney && availableJourneys.includes(requestedJourney)
      ? requestedJourney
      : availableJourneys[0] ?? "all";

  const timeClause = isAllTime ? "" : "AND ts_utc >= NOW() - ($2 * INTERVAL '1 minute')";
  const queryParams: Array<string | number> = isAllTime ? [effectiveJourney] : [effectiveJourney, minutes];

  // 2. Step-level aggregation directly from Supabase PostgreSQL
  const stepsRes = await pool.query<{
    step_id: string;
    total_events: string;
    unique_users: string;
    page_view_users: string;
    completed_users: string;
    abandoned_users: string;
    error_events: string;
    rage_events: string;
    avg_dwell_ms: string;
    avg_retries: string;
  }>(
    `
    WITH src AS (${srcSql}),
    filtered AS (
      SELECT *
      FROM src
      WHERE ($1 = 'all' OR journey_id = $1)
      ${timeClause}
    )
    SELECT
      step_id,
      COUNT(*)::text AS total_events,
      COUNT(DISTINCT COALESCE(NULLIF(user_id, ''), session_id, event_id))::text AS unique_users,
      COUNT(DISTINCT CASE WHEN event_type = 'page_view' THEN COALESCE(NULLIF(user_id, ''), session_id, event_id) END)::text AS page_view_users,
      COUNT(DISTINCT CASE WHEN event_type = 'step_complete' THEN COALESCE(NULLIF(user_id, ''), session_id, event_id) END)::text AS completed_users,
      COUNT(DISTINCT CASE WHEN event_type = 'abandon' THEN COALESCE(NULLIF(user_id, ''), session_id, event_id) END)::text AS abandoned_users,
      SUM(CASE WHEN event_type = 'error' THEN 1 ELSE 0 END)::text AS error_events,
      SUM(CASE WHEN event_type = 'rage_click' THEN 1 ELSE 0 END)::text AS rage_events,
      COALESCE(ROUND(AVG(CASE WHEN duration_ms > 0 THEN duration_ms END)::numeric, 0), 0)::text AS avg_dwell_ms,
      COALESCE(ROUND(AVG(
        CASE WHEN event_type = 'error' AND metadata IS NOT NULL AND metadata LIKE '%retry_count%'
        THEN CAST(NULLIF((metadata::jsonb)->>'retry_count', '') AS NUMERIC)
        END
      ), 2), 0)::text AS avg_retries
    FROM filtered
    WHERE step_id IS NOT NULL AND step_id <> ''
    GROUP BY step_id
    `,
    queryParams
  );

  // 3. Recent 25 events in this table, journey, and time window
  const eventsRes = await pool.query<{
    event_id: string;
    timestamp: Date;
    user_id: string | null;
    session_id: string | null;
    step_id: string | null;
    event_type: string | null;
    duration_ms: number | null;
    url: string | null;
  }>(
    `
    WITH src AS (${srcSql})
    SELECT
      event_id,
      ts_utc AS timestamp,
      user_id,
      session_id,
      step_id,
      event_type,
      duration_ms,
      url
    FROM src
    WHERE ($1 = 'all' OR journey_id = $1)
    ${timeClause}
    ORDER BY ts_utc DESC
    LIMIT 25
    `,
    queryParams
  );

  let totalEventsInWindow = 0;
  const rawSteps = stepsRes.rows.map((r) => {
    const totalEv = Number(r.total_events) || 0;
    totalEventsInWindow += totalEv;
    const uniqueUsers = Number(r.unique_users) || 0;
    const pageViewUsers = Number(r.page_view_users) || 0;
    const completedUsers = Number(r.completed_users) || 0;
    const abandonedUsers = Number(r.abandoned_users) || 0;
    const errorEvents = Number(r.error_events) || 0;
    const rageEvents = Number(r.rage_events) || 0;
    const avgDwellMs = Number(r.avg_dwell_ms) || 0;
    const avgRetries = Number(r.avg_retries) || 0;
    const effectiveUsers = pageViewUsers > 0 ? pageViewUsers : uniqueUsers;

    return {
      step_id: r.step_id,
      total_events: totalEv,
      users: effectiveUsers,
      unique_users: uniqueUsers,
      completion_rate_pct: uniqueUsers > 0 ? Math.min(100, Math.round((completedUsers / uniqueUsers) * 1000) / 10) : 0,
      abandon_rate_pct: uniqueUsers > 0 ? Math.min(100, Math.round((abandonedUsers / uniqueUsers) * 1000) / 10) : 0,
      error_rate_pct: uniqueUsers > 0 ? Math.min(100, Math.round((errorEvents / uniqueUsers) * 1000) / 10) : 0,
      avg_dwell_ms: avgDwellMs,
      avg_rage_clicks: uniqueUsers > 0 ? Math.round((rageEvents / uniqueUsers) * 100) / 100 : 0,
      avg_retries: avgRetries,
    };
  });

  // Sort by canonical step order if known for this journey; otherwise by descending user volume
  const canonical = CANONICAL_JOURNEY_STEPS[effectiveJourney];
  rawSteps.sort((a, b) => {
    if (canonical) {
      const idxA = canonical.indexOf(a.step_id);
      const idxB = canonical.indexOf(b.step_id);
      if (idxA !== -1 && idxB !== -1) return idxA - idxB;
      if (idxA !== -1) return -1;
      if (idxB !== -1) return 1;
    }
    return b.users - a.users;
  });

  // Keep top 12 stages for clean visualization when viewing "all"
  const orderedSteps = rawSteps.slice(0, 12);

  // Build funnel with real drop-off percentages between consecutive stages
  const funnel = orderedSteps.map((s, idx) => {
    const next = orderedSteps[idx + 1];
    let dropOffPct = 0;
    if (next && s.users > 0) {
      dropOffPct =
        next.users < s.users
          ? Math.round(((s.users - next.users) / s.users) * 1000) / 10
          : 0;
    } else if (!next && s.abandon_rate_pct > 0) {
      dropOffPct = s.abandon_rate_pct;
    }
    return {
      step_id: s.step_id,
      users: s.users,
      drop_off_pct: dropOffPct,
    };
  });

  const steps = orderedSteps.map((s) => ({
    step_id: s.step_id,
    unique_users: s.unique_users,
    completion_rate_pct: s.completion_rate_pct,
    abandon_rate_pct: s.abandon_rate_pct,
    error_rate_pct: s.error_rate_pct,
    avg_dwell_ms: s.avg_dwell_ms,
    avg_rage_clicks: s.avg_rage_clicks,
    avg_retries: s.avg_retries,
  }));

  let overallCompletionPct = 0;
  if (funnel.length > 1) {
    const firstUsers = funnel[0]?.users ?? 0;
    const lastUsers = funnel[funnel.length - 1]?.users ?? 0;
    if (firstUsers > 0) {
      overallCompletionPct = Math.min(100, Math.round((lastUsers / firstUsers) * 1000) / 10);
    }
  } else if (funnel.length === 1) {
    overallCompletionPct = steps[0]?.completion_rate_pct ?? 100;
  }

  // Real algorithmic friction scoring per stage
  const frictionScores = funnel.map((f) => {
    const m = steps.find((st) => st.step_id === f.step_id);
    const drop = f.drop_off_pct;
    const err = m?.error_rate_pct ?? 0;
    const rage = m?.avg_rage_clicks ?? 0;
    const dwell = m?.avg_dwell_ms ?? 0;
    const retries = m?.avg_retries ?? 0;

    const dropScore = drop * 0.55;
    const errScore = Math.min(35, err * 1.4);
    const rageScore = Math.min(30, rage * 24);
    const dwellScore = dwell > 20000 ? Math.min(20, ((dwell - 20000) / 60000) * 18) : 0;

    const score = Math.min(100, Math.max(0, Math.round(dropScore + errScore + rageScore + dwellScore)));
    const signals: string[] = [];
    if (drop >= 25) signals.push("high_dropoff");
    if (err >= 5) signals.push("error_spike");
    if (rage >= 0.2) signals.push("rage_clicks");
    if (dwell >= 35000) signals.push("dwell_deviation");
    if (retries >= 1.5) signals.push("retry_loop");

    const confidence = (m?.unique_users ?? 0) >= 30 ? "high" : (m?.unique_users ?? 0) >= 8 ? "medium" : "low";
    return {
      step_id: f.step_id,
      score,
      is_critical: score >= 35,
      signals,
      confidence,
    };
  });

  const overallFriction =
    frictionScores.length > 0
      ? Math.round(frictionScores.reduce((acc, s) => acc + s.score, 0) / frictionScores.length)
      : 0;
  const criticalSteps = frictionScores.filter((s) => s.is_critical).map((s) => s.step_id);

  const events = eventsRes.rows.map((e) => ({
    event_id: String(e.event_id),
    timestamp: e.timestamp instanceof Date ? e.timestamp.toISOString() : String(e.timestamp),
    user_id: e.user_id,
    session_id: e.session_id,
    step_id: e.step_id,
    event_type: e.event_type,
    duration_ms: e.duration_ms,
    url: e.url,
  }));

  return {
    effectiveJourney,
    availableJourneys,
    totalEventsInWindow,
    overallCompletionPct,
    funnel,
    steps,
    friction: {
      threshold: 60,
      overallScore: overallFriction,
      criticalSteps,
      scores: frictionScores,
    },
    events,
  };
}

function buildHeuristicInsights(
  table: AnalyticsTable,
  journeyId: string,
  windowLabel: string,
  totalEvents: number,
  funnel: Array<{ step_id: string; users: number; drop_off_pct: number }>,
  steps: NonNullable<LiveTelemetryPayload["metrics"]>["steps"],
  friction: NonNullable<LiveTelemetryPayload["friction"]>,
  completionPct: number
): LiveTelemetryPayload["insights"] {
  if (funnel.length === 0 || totalEvents === 0) {
    return [
      {
        id: `ins-empty-${table}-${windowLabel}`,
        title: `No Events Recorded in ${windowLabel} Window`,
        description: `Zero telemetry events were found in Supabase table '${table}' for journey '${journeyId}' during the last ${windowLabel}. Expand the time filter (e.g. 24h, 30d, or All) or switch to 'veriscape_trial_events' to inspect active sessions.`,
        severity: "minor",
        confidence: 99,
        recommendation: `Switch the time window to 24h, 30d, or All, or trigger live traffic on your monitored application.`,
        detectedAt: "Supabase Query Engine",
      },
    ];
  }

  const list: LiveTelemetryPayload["insights"] = [];
  const worstDrop = [...funnel].sort((a, b) => b.drop_off_pct - a.drop_off_pct)[0];
  const worstError = [...steps].sort((a, b) => b.error_rate_pct - a.error_rate_pct)[0];
  const worstRage = [...steps].sort((a, b) => b.avg_rage_clicks - a.avg_rage_clicks)[0];
  const worstDwell = [...steps].sort((a, b) => b.avg_dwell_ms - a.avg_dwell_ms)[0];
  const totalUsers = funnel[0]?.users ?? 0;
  const convertedUsers = funnel.length > 1 ? (funnel[funnel.length - 1]?.users ?? 0) : totalUsers;

  if (worstDrop && worstDrop.drop_off_pct > 0) {
    list.push({
      id: `ins-drop-${table}-${windowLabel}`,
      title: `Primary Drop-Off Cliff at ${worstDrop.step_id.replace(/[_-]/g, " ")}`,
      description: `Across ${totalEvents.toLocaleString()} events (${totalUsers.toLocaleString()} entrants) in [${table}] over [${windowLabel}], stage '${worstDrop.step_id}' loses ${worstDrop.drop_off_pct.toFixed(1)}% of users before the next step.`,
      severity: worstDrop.drop_off_pct >= 30 ? "critical" : "urgent",
      confidence: 95,
      recommendation: `Streamline '${worstDrop.step_id}' interactions, remove blocking async steps, and monitor submission latency.`,
      detectedAt: `Telemetry Engine (${table} · ${windowLabel})`,
    });
  }

  if (worstError && worstError.error_rate_pct > 0) {
    list.push({
      id: `ins-err-${table}-${windowLabel}`,
      title: `Elevated Error Rate on ${worstError.step_id.replace(/[_-]/g, " ")}`,
      description: `Stage '${worstError.step_id}' recorded a ${worstError.error_rate_pct.toFixed(1)}% error rate (${worstError.avg_retries.toFixed(1)} avg retries/error) inside [${table}] during [${windowLabel}].`,
      severity: worstError.error_rate_pct >= 12 ? "critical" : "urgent",
      confidence: 93,
      recommendation: `Inspect backend timeouts and client-side validation handlers on '${worstError.step_id}' to stop retry loops.`,
      detectedAt: `Telemetry Engine (${table} · ${windowLabel})`,
    });
  }

  if (worstRage && worstRage.avg_rage_clicks > 0.1) {
    list.push({
      id: `ins-rage-${table}-${windowLabel}`,
      title: `Rage Click Spike on ${worstRage.step_id.replace(/[_-]/g, " ")}`,
      description: `Users triggered ${worstRage.avg_rage_clicks.toFixed(2)} rage clicks per user on '${worstRage.step_id}' in [${table}] (${windowLabel}), indicating unresponsive controls or delayed UI feedback.`,
      severity: worstRage.avg_rage_clicks >= 0.35 ? "critical" : "urgent",
      confidence: 91,
      recommendation: `Add immediate disabled/loading feedback and inspect interactive hit targets on '${worstRage.step_id}'.`,
      detectedAt: `Telemetry Engine (${table} · ${windowLabel})`,
    });
  } else if (worstDwell && worstDwell.avg_dwell_ms >= 30000) {
    list.push({
      id: `ins-dwell-${table}-${windowLabel}`,
      title: `High Dwell Latency on ${worstDwell.step_id.replace(/[_-]/g, " ")}`,
      description: `Average dwell time reached ${(worstDwell.avg_dwell_ms / 1000).toFixed(1)}s on '${worstDwell.step_id}' in [${table}] (${windowLabel}), well above the 20s benchmark.`,
      severity: "urgent",
      confidence: 90,
      recommendation: `Break '${worstDwell.step_id}' into faster sub-steps and preload required assets asynchronously.`,
      detectedAt: `Telemetry Engine (${table} · ${windowLabel})`,
    });
  }

  list.push({
    id: `ins-summary-${table}-${windowLabel}`,
    title: `Funnel Health Summary (${table} · ${windowLabel})`,
    description: `Evaluated ${totalEvents.toLocaleString()} events across ${funnel.length} stages of '${journeyId}'. ${convertedUsers.toLocaleString()} of ${totalUsers.toLocaleString()} entrants completed the flow (${completionPct.toFixed(1)}% conversion, avg friction ${friction.overallScore}/100).`,
    severity: completionPct < 20 ? "urgent" : "minor",
    confidence: 97,
    recommendation: `Prioritize remediation on '${friction.criticalSteps[0] || worstDrop?.step_id || funnel[0]?.step_id}' to capture the highest conversion uplift.`,
    detectedAt: `Telemetry Engine (${table} · ${windowLabel})`,
  });

  return list;
}

async function resolveAnalytics(
  requestedJourney: string | null,
  table: AnalyticsTable,
  minutes: number,
  isExplicitRun = false,
  customLlmConfig?: CustomLlmConfig
): Promise<LiveTelemetryPayload> {
  const windowLabel = formatWindowLabel(minutes);

  // Optional trigger of backend LangGraph run on explicit click
  let runId: string | null = null;
  if (isExplicitRun) {
    try {
      const runRes = await startRun(requestedJourney || "quest_journey", {
        autoApprove: true,
        windowMinutes: Math.min(43200, Math.max(1, minutes)),
      });
      if (runRes.ok) {
        runId = runRes.data.run_id;
      }
    } catch {
      // Direct Supabase + Groq pipeline continues seamlessly
    }
  }

  const dbData = await querySupabaseAnalytics(table, requestedJourney, minutes);
  const journeyId = dbData.effectiveJourney;
  const { funnel, steps, friction, events, availableJourneys, totalEventsInWindow, overallCompletionPct } = dbData;

  const fallbackInsights = buildHeuristicInsights(
    table,
    journeyId,
    windowLabel,
    totalEventsInWindow,
    funnel,
    steps,
    friction,
    overallCompletionPct
  );

  // Groq LLM Inference (live on Run Analysis, or cached per table|journey|window|eventCount on filter switches)
  const groqApiKey =
    customLlmConfig?.apiKey?.trim() ||
    process.env.GROQ_API_KEY?.trim() ||
    process.env.CJI_GROQ_API_KEY?.trim() ||
    "";
  const groqModel =
    customLlmConfig?.model?.trim() ||
    process.env.GROQ_MODEL?.trim() ||
    process.env.LLM_MODEL?.trim() ||
    "openai/gpt-oss-120b";

  let groqResult: { insights: LiveTelemetryPayload["insights"]; narrative?: string | undefined } | null = null;
  const cacheKey = `${table}|${journeyId}|${minutes}|${totalEventsInWindow}|${groqModel}`;

  if (groqApiKey && funnel.length > 0 && totalEventsInWindow > 0) {
    const cached = groqCache.get(cacheKey);
    if (!isExplicitRun && cached && cached.expiresAt > Date.now()) {
      groqResult = cached.result;
    } else {
      groqResult = await generateGroqInsights(
        groqApiKey,
        groqModel,
        journeyId,
        table,
        windowLabel,
        totalEventsInWindow,
        funnel,
        steps,
        friction,
        overallCompletionPct
      );
      if (groqResult) {
        groqCache.set(cacheKey, {
          expiresAt: Date.now() + 3 * 60 * 1000,
          result: groqResult,
        });
      }
    }
  }

  const insightsList =
    groqResult?.insights && groqResult.insights.length > 0 ? groqResult.insights : fallbackInsights;

  const topFrictionStep = [...friction.scores].sort((a, b) => b.score - a.score)[0];
  const executiveNarrative =
    groqResult?.narrative ||
    (totalEventsInWindow === 0
      ? `No telemetry events were recorded in Supabase table [${table}] for journey [${journeyId}] during the [${windowLabel}] window. Expand the lookback filter to 24h, 30d, or All to analyze earlier sessions.`
      : `Autonomous telemetry evaluation of Supabase table [${table}] for journey [${journeyId}] across the [${windowLabel}] window analyzed ${totalEventsInWindow.toLocaleString()} events (${(funnel[0]?.users ?? 0).toLocaleString()} entrants). Funnel conversion stands at ${overallCompletionPct.toFixed(1)}% with an average friction index of ${friction.overallScore}/100. Primary bottleneck is [${topFrictionStep?.step_id ?? "none"}] (friction ${topFrictionStep?.score ?? 0}/100; signals: ${topFrictionStep?.signals.join(", ") || "none"}).`);

  // Compile table- & window-specific HTML report so switching table/window ALWAYS updates reports
  const scopeKey = `${table}|${journeyId}`;
  const existingReports = scopedCompiledReports.get(scopeKey) ?? [];
  const reportId = `rep_${table}_${journeyId}_${windowLabel}_${Date.now().toString(36)}`;
  const reportHtml = buildReportHtml(
    reportId,
    journeyId,
    table,
    windowLabel,
    totalEventsInWindow,
    executiveNarrative,
    insightsList,
    funnel,
    friction,
    overallCompletionPct
  );

  const shouldCreateNewReport =
    isExplicitRun ||
    existingReports.length === 0 ||
    existingReports[0]?.window_label !== windowLabel ||
    existingReports[0]?.summary?.totalEvents !== totalEventsInWindow;

  if (shouldCreateNewReport) {
    runtimeHtmlReports.set(reportId, reportHtml);
    runtimeHtmlReports.set(`rep_${table}_${journeyId}_${windowLabel}`, reportHtml);

    const freshReport: CompiledReportItem = {
      report_id: reportId,
      run_id: runId || `run_${Date.now().toString(36)}`,
      journey_id: journeyId,
      table,
      window_label: windowLabel,
      size_bytes: Buffer.byteLength(reportHtml, "utf-8"),
      created_at: new Date().toISOString(),
      content_url: `/reports/${reportId}`,
      narrative: executiveNarrative,
      insights: insightsList,
      summary: {
        totalSessions: funnel[0]?.users ?? 0,
        totalEvents: totalEventsInWindow,
        completionPct: overallCompletionPct,
        avgFriction: friction.overallScore,
        criticalCount: friction.criticalSteps.length,
        topBottleneck: topFrictionStep?.step_id ?? "none",
      },
    };
    const nextList = [freshReport, ...existingReports.filter((r) => r.window_label !== windowLabel)].slice(0, 8);
    scopedCompiledReports.set(scopeKey, nextList);
  } else if (existingReports[0]) {
    // Keep HTML synced with latest Groq output
    runtimeHtmlReports.set(existingReports[0].report_id, reportHtml);
    existingReports[0].narrative = executiveNarrative;
    existingReports[0].insights = insightsList;
  }

  const reportsList = scopedCompiledReports.get(scopeKey) ?? [];

  return {
    journeyId,
    selectedTable: table,
    windowMinutes: minutes,
    windowLabel,
    totalEventsInWindow,
    mode: "realtime",
    isLiveSupabase: true,
    status: "connected",
    statusMessage:
      totalEventsInWindow > 0
        ? `Live Supabase [${table}] · ${journeyId} · ${totalEventsInWindow.toLocaleString()} events (${windowLabel})`
        : `Live Supabase [${table}] · 0 events in ${windowLabel} window`,
    metrics: {
      overallCompletionPct,
      funnel,
      steps,
    },
    friction,
    events,
    insights: insightsList,
    reports: reportsList,
    narrative: executiveNarrative,
    availableJourneys,
    lastUpdated: new Date().toISOString(),
  };
}

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const minutes = Number(searchParams.get("minutes") ?? "60");
  const requestedJourney = searchParams.get("journey_id");
  const table = normalizeTable(searchParams.get("table"));

  const customKey = request.headers.get("x-groq-key") || undefined;
  const customModel = request.headers.get("x-llm-model") || undefined;
  const customProvider = request.headers.get("x-llm-provider") || undefined;

  const customLlmConfig: CustomLlmConfig | undefined = customKey
    ? {
        provider: customProvider || "groq",
        apiKey: customKey,
        model: customModel,
      }
    : undefined;

  try {
    const payload = await resolveAnalytics(requestedJourney, table, minutes, false, customLlmConfig);
    return NextResponse.json(payload);
  } catch (err) {
    return NextResponse.json(
      {
        journeyId: requestedJourney ?? "quest_journey",
        selectedTable: table,
        windowMinutes: minutes,
        windowLabel: formatWindowLabel(minutes),
        totalEventsInWindow: 0,
        mode: "realtime",
        isLiveSupabase: false,
        status: "error",
        statusMessage: `Supabase telemetry query error: ${err instanceof Error ? err.message : String(err)}`,
        metrics: { overallCompletionPct: 0, funnel: [], steps: [] },
        friction: { threshold: 60, overallScore: 0, criticalSteps: [], scores: [] },
        events: [],
        insights: [],
        reports: [],
        availableJourneys: ["all"],
        lastUpdated: new Date().toISOString(),
      },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  let minutes = 60;
  let requestedJourney: string | null = null;
  let table: AnalyticsTable = "veriscape_trial_events";
  let customLlmConfig: CustomLlmConfig | undefined = undefined;

  const customHeaderKey = request.headers.get("x-groq-key") || undefined;
  const customHeaderModel = request.headers.get("x-llm-model") || undefined;
  const customHeaderProvider = request.headers.get("x-llm-provider") || undefined;

  try {
    const body = await request.json().catch(() => ({}));
    if (body.minutes !== undefined) minutes = Number(body.minutes);
    if (body.journey_id) requestedJourney = String(body.journey_id);
    if (body.table) table = normalizeTable(String(body.table));
    if (body.llm_config && typeof body.llm_config === "object") {
      customLlmConfig = {
        provider: body.llm_config.provider || customHeaderProvider || "groq",
        apiKey: body.llm_config.apiKey || customHeaderKey,
        model: body.llm_config.model || customHeaderModel,
        baseUrl: body.llm_config.baseUrl,
      };
    } else if (customHeaderKey) {
      customLlmConfig = {
        provider: customHeaderProvider || "groq",
        apiKey: customHeaderKey,
        model: customHeaderModel,
      };
    }
  } catch {
    const { searchParams } = request.nextUrl;
    if (searchParams.get("minutes")) minutes = Number(searchParams.get("minutes"));
    if (searchParams.get("journey_id")) requestedJourney = searchParams.get("journey_id");
    if (searchParams.get("table")) table = normalizeTable(searchParams.get("table"));
  }

  try {
    const payload = await resolveAnalytics(requestedJourney, table, minutes, true, customLlmConfig);
    return NextResponse.json(payload);
  } catch (err) {
    return NextResponse.json(
      {
        journeyId: requestedJourney ?? "quest_journey",
        selectedTable: table,
        windowMinutes: minutes,
        windowLabel: formatWindowLabel(minutes),
        totalEventsInWindow: 0,
        mode: "realtime",
        isLiveSupabase: false,
        status: "error",
        statusMessage: `Analysis run error: ${err instanceof Error ? err.message : String(err)}`,
        metrics: { overallCompletionPct: 0, funnel: [], steps: [] },
        friction: { threshold: 60, overallScore: 0, criticalSteps: [], scores: [] },
        events: [],
        insights: [],
        reports: [],
        availableJourneys: ["all"],
        lastUpdated: new Date().toISOString(),
      },
      { status: 500 }
    );
  }
}
