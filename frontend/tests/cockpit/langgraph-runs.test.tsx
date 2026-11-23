import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { AnalyticsScreen } from "@/cockpit/components/screens/AnalyticsScreen";

describe("AnalyticsScreen - LangGraph Multi-Agent Runs & Inspector", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders LangGraph workflow controls in the analytics toolbar", () => {
    render(<AnalyticsScreen />);
    
    // Auto-Approve toggle
    const toggleBtn = screen.getByRole("button", { name: /auto-approve/i });
    expect(toggleBtn).toBeInTheDocument();

    // Agent Runs inspector button
    const runsBtn = screen.getByRole("button", { name: /agent runs/i });
    expect(runsBtn).toBeInTheDocument();

    // Run Analysis primary button
    const runBtn = screen.getByRole("button", { name: /run analysis/i });
    expect(runBtn).toBeInTheDocument();
  });

  it("toggles between Auto-Approve and Human Gate modes", () => {
    render(<AnalyticsScreen />);
    
    const toggleBtn = screen.getByRole("button", { name: /auto-approve/i });
    expect(toggleBtn).toHaveTextContent(/auto-approve/i);

    fireEvent.click(toggleBtn);
    expect(screen.getByRole("button", { name: /human gate/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /human gate/i }));
    expect(screen.getByRole("button", { name: /auto-approve/i })).toBeInTheDocument();
  });

  it("opens and closes the Workflow Runs Inspector modal", async () => {
    // Mock fetch for /api/runs
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/api/runs")) {
        return new Response(
          JSON.stringify({
            ok: true,
            data: {
              items: [
                {
                  run_id: "run-test-12345678",
                  journey_id: "quest_journey",
                  mode: "realtime",
                  status: "completed",
                  created_at: new Date().toISOString(),
                  updated_at: new Date().toISOString(),
                  report_id: "rep-001",
                },
              ],
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response(JSON.stringify({ ok: true, metrics: { funnel: [] } }), { status: 200 });
    });

    render(<AnalyticsScreen />);
    
    const runsBtn = screen.getByRole("button", { name: /agent runs/i });
    fireEvent.click(runsBtn);

    await waitFor(() => {
      expect(screen.getByText(/langgraph workflow runs & agent inspector/i)).toBeInTheDocument();
      expect(screen.getByText(/run-test-1/i)).toBeInTheDocument();
    });

    // Close button
    const closeBtn = screen.getByRole("button", { name: /close runs inspector/i });
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByText(/langgraph workflow runs & agent inspector/i)).not.toBeInTheDocument();
    });
  });

  it("dispatches POST /api/runs on clicking Run Analysis and displays the 5-node agent rail", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url);
      const method = init?.method || "GET";

      if (u.includes("/api/runs") && method === "POST") {
        return new Response(
          JSON.stringify({
            ok: true,
            data: {
              run_id: "run-live-abc12345",
              journey_id: "quest_journey",
              mode: "realtime",
              status: "running",
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              steps: {
                ingestion_worker: { status: "completed", started_at: new Date().toISOString(), finished_at: new Date().toISOString() },
                data_worker: { status: "running", started_at: new Date().toISOString() },
                friction_worker: { status: "pending" },
                insight_worker: { status: "pending" },
                report_worker: { status: "pending" },
              },
            },
          }),
          { status: 202, headers: { "Content-Type": "application/json" } }
        );
      }

      if (u.includes("/api/runs/run-live-abc12345")) {
        return new Response(
          JSON.stringify({
            ok: true,
            data: {
              run_id: "run-live-abc12345",
              journey_id: "quest_journey",
              status: "awaiting_approval",
              steps: {
                ingestion_worker: { status: "completed" },
                data_worker: { status: "completed" },
                friction_worker: { status: "completed" },
                insight_worker: { status: "completed" },
                report_worker: { status: "pending" },
              },
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      return new Response(JSON.stringify({ ok: true, metrics: { funnel: [] } }), { status: 200 });
    });

    render(<AnalyticsScreen />);

    const runBtn = screen.getByRole("button", { name: /run analysis/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/runs",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("quest_journey"),
        })
      );
    });

    // Check that LangGraph 5-node pipeline is rendered in the UI
    await waitFor(() => {
      expect(screen.getByText(/langgraph autonomous multi-agent pipeline/i)).toBeInTheDocument();
      expect(screen.getByText("Ingestion")).toBeInTheDocument();
      expect(screen.getByText("Aggregator")).toBeInTheDocument();
      expect(screen.getByText("Friction MCP")).toBeInTheDocument();
      expect(screen.getByText("Insight Agent")).toBeInTheDocument();
      expect(screen.getByText("Report Server")).toBeInTheDocument();
    });
  });
});
