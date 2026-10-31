/** Spec 14 views: success, empty, problem and permission states with axe checks (design §6). */
import { render, screen, within } from "@testing-library/react";

import { ActionForm } from "@/components/ActionForm";
import { ValidationSummary } from "@/components/Ingest";
import { ProvenanceBadge } from "@/components/Insights";
import { IDLE } from "@/lib/action-state";
import { failed, ok, type Problem } from "@/lib/api/problem";
import { MetricsView, WindowSelector } from "@/views/journeys";
import { ReportListView } from "@/views/reports";
import { RunResultsView } from "@/views/run-results";
import { RunDetailView } from "@/views/runs";
import { StepEventsView, StepFrictionView, StepInsightView, StepMetricsView } from "@/views/step-detail";

import { axeViolations } from "../support/axe";
import * as fx from "../support/fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const P503: Problem = { status: 503, code: "storage_unavailable", title: "Storage unavailable", detail: "Retry later.", requestId: "req-9", retryAfterS: 5 };

async function expectAccessible(container: Element) {
  expect(await axeViolations(container)).toEqual([]);
}

describe("journey analytics", () => {
  it("formats funnel values and links steps to their drill-down", async () => {
    const { container } = render(<MetricsView result={ok(fx.metrics)} />);
    const funnel = screen.getByRole("table", { name: "Funnel" });
    const row = within(funnel).getByRole("row", { name: /signup_form/ });
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(["1,640", "18.0%"]);
    const metrics = screen.getByRole("table", { name: "Step metrics" });
    expect(within(metrics).getByRole("link", { name: "landing_page" })).toHaveAttribute(
      "href",
      "/journeys/user_onboarding/steps/landing_page",
    );
    expect(within(metrics).getAllByRole("cell").map((c) => c.textContent)).toEqual([
      "2,000", "91.5%", "8.5%", "0.4%", "5.2 s", "0.10", "0.00",
    ]);
    await expectAccessible(container);
  });

  it("offers days for demo data and minutes for realtime data", () => {
    const { unmount } = render(<WindowSelector journey={fx.journey} window={{ days: 7 }} />);
    expect(screen.getByLabelText("Analysis window")).toHaveAttribute("name", "days");
    expect(screen.getByLabelText("Analysis window")).toHaveValue("7");
    unmount();
    render(<WindowSelector journey={{ ...fx.journey, mode: "realtime" }} window={{}} />);
    expect(screen.getByLabelText("Analysis window")).toHaveAttribute("name", "minutes");
    expect(screen.getByLabelText("Analysis window")).toHaveValue("60");
  });
});

describe("step drill-down", () => {
  it("shows the step's metrics, friction score and insight as given", async () => {
    const { container } = render(
      <>
        <StepMetricsView stepId="signup_form" result={ok(fx.metrics)} />
        <StepFrictionView stepId="payment_info" result={ok(fx.friction)} />
        <StepInsightView stepId="payment_info" result={ok(fx.insights)} />
      </>,
    );
    expect(screen.getByText("2 of 3")).toBeInTheDocument();
    expect(screen.getByText("78")).toBeInTheDocument();
    expect(screen.getByText("high_drop_off, rage_clicks")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Card form rejects valid input" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: fx.RUN_ID })).toHaveAttribute("href", `/runs/${fx.RUN_ID}`);
    await expectAccessible(container);
  });

  it("has empty states for unknown steps", () => {
    render(
      <>
        <StepMetricsView stepId="nope" result={ok(fx.metrics)} />
        <StepFrictionView stepId="nope" result={ok(fx.friction)} />
        <StepInsightView stepId="nope" result={ok({ ...fx.insights, run_id: null, insights: [] })} />
      </>,
    );
    expect(screen.getByText("No metrics for this step in the selected window.")).toBeInTheDocument();
    expect(screen.getByText("No friction score for this step in the selected window.")).toBeInTheDocument();
    expect(screen.getByText("No run has insights yet.")).toBeInTheDocument();
  });

  it("lists events with a pager for operators and a permission text for viewers", async () => {
    const { container, rerender } = render(
      <StepEventsView allowed result={ok(fx.events)} basePath="/journeys/j/steps/s" eventType="error" />,
    );
    expect(screen.getAllByRole("row")).toHaveLength(3);
    const next = screen.getByRole("link", { name: "Older events" }).getAttribute("href") ?? "";
    expect(next).toMatch(/^\/journeys\/j\/steps\/s\?event_type=error&cursor=/);
    await expectAccessible(container);
    rerender(<StepEventsView allowed={false} result={null} basePath="/x" eventType={undefined} />);
    expect(screen.getByText(/Events are only listed for operators/)).toBeInTheDocument();
    rerender(<StepEventsView allowed result={failed(P503)} basePath="/x" eventType={undefined} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Events: Storage unavailable");
  });
});

describe("run results and provenance", () => {
  it("labels each source and shows usage", async () => {
    const { container } = render(<RunResultsView result={ok(fx.runResults)} />);
    expect(screen.getAllByText("Written by the language model (openai/gpt-oss-120b, groq)")).toHaveLength(2);
    expect(screen.getByText("Fallback text, not written by the language model (reason: llm_disabled)")).toBeInTheDocument();
    expect(screen.getByText("Provenance not recorded (run created before Spec 14)")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Prioritized fixes/ })).toBeInTheDocument();
    expect(screen.getByText("1,200")).toBeInTheDocument();
    expect(screen.getByText("No errors recorded.")).toBeInTheDocument();
    await expectAccessible(container);
  });

  it("has empty and problem states", () => {
    const empty = { ...fx.runResults, status: "running" as const, narrative: null, insights: [], prioritized_fixes: [], friction_scores: [] };
    const { rerender } = render(<RunResultsView result={ok(empty)} />);
    expect(screen.getByText(/No narrative yet/)).toBeInTheDocument();
    expect(screen.getByText("Insights are not generated yet.")).toBeInTheDocument();
    rerender(<RunResultsView result={failed(P503)} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Run results: Storage unavailable");
    expect(screen.getByText("Try again in 5 seconds.")).toBeInTheDocument();
  });

  it("shows ingestion results and files waiting for review", () => {
    render(
      <RunResultsView
        result={ok({
          ...fx.runResults,
          ingestion_results: [{ file_name: "ga4.json", detected_source: "ga4", confidence: 0.92, records_written: 10, records_skipped: 1, status: "success", cached_mapping: false }],
          ingestion_pending_review: [{ file_name: "odd.csv", detected_source: "unknown", confidence: 0.41, flagged_at: "2026-10-28T21:50:00Z" }],
        })}
      />,
    );
    expect(screen.getByRole("table", { name: "Files ingested by this run" })).toHaveTextContent("ga4.json");
    expect(screen.getByText(/odd.csv \(detected unknown, confidence 0.41\)/)).toBeInTheDocument();
  });

  it("badge texts", () => {
    render(<ProvenanceBadge provenance={{ source: "llm", model: null, provider: null, reason: null, generated_at: null }} />);
    expect(screen.getByText("Written by the language model")).toBeInTheDocument();
  });
});

describe("run detail", () => {
  it("links preview and download and renders the actions slot", () => {
    render(<RunDetailView result={ok(fx.run)} actions={<p>actions here</p>} />);
    expect(screen.getByRole("link", { name: "Download report" })).toHaveAttribute("href", `/reports/${fx.REPORT_ID}/download`);
    expect(screen.getByText("actions here")).toBeInTheDocument();
  });

  it("mentions resume for failed runs", () => {
    render(<RunDetailView result={ok(fx.failedRun)} />);
    expect(screen.getByText(/Resume the run on this page/)).toBeInTheDocument();
  });
});

describe("reports", () => {
  it("lists reports with preview and download links", async () => {
    const { container } = render(<ReportListView result={ok(fx.reports)} journeyId={undefined} />);
    expect(screen.getByRole("link", { name: /^Download/ })).toHaveAttribute("href", `/reports/${fx.REPORT_ID}/download`);
    expect(screen.getByText("20 KiB")).toBeInTheDocument();
    expect(screen.getByText("End of the list.")).toBeInTheDocument();
    await expectAccessible(container);
  });

  it("pages with the cursor and has an empty state", () => {
    const { rerender } = render(
      <ReportListView result={ok({ ...fx.reports, page: { limit: 25, next_cursor: "abc.def" } })} journeyId="user_onboarding" />,
    );
    expect(screen.getByRole("link", { name: "Older reports" })).toHaveAttribute(
      "href",
      "/reports?journey_id=user_onboarding&cursor=abc.def",
    );
    rerender(<ReportListView result={ok({ data: [], page: { limit: 25, next_cursor: null } })} journeyId={undefined} />);
    expect(screen.getByRole("status")).toHaveTextContent("No reports yet.");
  });
});

describe("ingestion", () => {
  it("summarises a validation without user or session ids", async () => {
    const { container } = render(<ValidationSummary validation={fx.validation} />);
    expect(screen.getByText(/Nothing has been written yet/)).toBeInTheDocument();
    expect(screen.getByText("JSON array")).toBeInTheDocument();
    expect(screen.getByText(/Journey steps without any row in this file: payment_info/)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Steps found in the file" })).toHaveTextContent("unknown_step");
    expect(container.textContent).not.toMatch(/user_id|session_id/);
    await expectAccessible(container);
  });
});

describe("action form", () => {
  const action = vi.fn(async () => IDLE);

  it("explains a disabled action", async () => {
    const { container } = render(
      <ActionForm action={action} fields={{ key: "key-00000001" }} label="Approve run" pendingLabel="Approving…" what="Approve run" disabledReason="Requires the operator role." />,
    );
    const button = screen.getByRole("button", { name: "Approve run" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("Requires the operator role.");
    expect(container.querySelector('input[name="key"]')).toHaveValue("key-00000001");
    await expectAccessible(container);
  });

  it("is enabled without a reason", () => {
    render(<ActionForm action={action} fields={{}} label="Resume run" pendingLabel="Resuming…" what="Resume run" />);
    expect(screen.getByRole("button", { name: "Resume run" })).toBeEnabled();
  });
});
