import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AnalyticsScreen } from "@/cockpit/components/screens/AnalyticsScreen";

// Mock fetch for /api/analytics
global.fetch = vi.fn(() =>
  Promise.resolve({
    ok: true,
    json: () =>
      Promise.resolve({
        journeyId: "user_onboarding",
        windowMinutes: 60,
        mode: "realtime",
        isLiveSupabase: true,
        status: "connected",
        statusMessage: "Connected to Supabase PostgreSQL (60m lookback)",
        metrics: {
          overallCompletionPct: 68.4,
          funnel: [
            { step_id: "landing_page", users: 1000, drop_off_pct: 10 },
            { step_id: "sign_up_form", users: 900, drop_off_pct: 20 },
            { step_id: "email_verification", users: 720, drop_off_pct: 35 },
          ],
          steps: [],
        },
        friction: {
          threshold: 60,
          overallScore: 42,
          criticalSteps: ["email_verification"],
          scores: [
            { step_id: "landing_page", score: 12, is_critical: false, signals: [], confidence: "high" },
            { step_id: "email_verification", score: 75, is_critical: true, signals: ["rage_clicks"], confidence: "high" },
          ],
        },
        events: [
          {
            event_id: "evt-test-1",
            timestamp: new Date().toISOString(),
            user_id: "u123",
            session_id: "s456",
            step_id: "email_verification",
            event_type: "rage_click",
            duration_ms: 120,
            url: "/verify",
          },
        ],
        insights: [],
        availableJourneys: ["user_onboarding"],
        lastUpdated: new Date().toISOString(),
      }),
  })
) as unknown as typeof fetch;

describe("AnalyticsScreen", () => {
  it("renders the top bento metrics and sub-navigation", () => {
    render(<AnalyticsScreen />);
    expect(screen.getByText("Live Funnel Volume")).toBeInTheDocument();
    expect(screen.getByText("Avg. Friction Score")).toBeInTheDocument();
    expect(screen.getByText("Monitored Funnel Steps")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Journey Funnel/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Friction Analytics/ })).toBeInTheDocument();
  });

  it("switches sub-tabs and displays their respective content", async () => {
    render(<AnalyticsScreen />);

    // Click Journey Funnel tab
    const journeyTab = screen.getByRole("button", { name: /Journey Funnel/ });
    fireEvent.click(journeyTab);
    expect(screen.getByText("Step-by-Step Funnel Progression")).toBeInTheDocument();

    // Click Friction Analytics tab
    const frictionTab = screen.getByRole("button", { name: /Friction Analytics/ });
    fireEvent.click(frictionTab);
    expect(screen.getByText("Friction Diagnostics & Scoring")).toBeInTheDocument();

    // Click Machine Insights tab
    const insightsTab = screen.getByRole("button", { name: /Machine Insights/ });
    fireEvent.click(insightsTab);
    expect(screen.getByText("Strategic Machine Intelligence Insights")).toBeInTheDocument();

    // Click Tactical Reports tab
    const reportsTab = screen.getByRole("button", { name: /Tactical Reports/ });
    fireEvent.click(reportsTab);
    expect(screen.getByText(/Tactical Analytics Reports/)).toBeInTheDocument();
  });

  it("renders the Run Analysis button and executes analysis pipeline", async () => {
    render(<AnalyticsScreen />);

    const runAnalysisBtn = screen.getAllByRole("button", { name: /Run Analysis|Run Journey Analysis/i })[0]!;
    expect(runAnalysisBtn).toBeInTheDocument();

    fireEvent.click(runAnalysisBtn);
    expect(runAnalysisBtn).toBeDisabled();
  });
});

