/** Each view's success, empty and problem states, with axe checks (Spec 13, OD-135, OD-137). */
import { render, screen, within } from "@testing-library/react";

import { failed, ok, type Problem } from "@/lib/api/problem";
import { FrictionView, JourneyListView, JourneyStepsView, MetricsView } from "@/views/journeys";
import { parseStatus, RunDetailView, RunFilter, RunListView } from "@/views/runs";
import { HealthDetailsView, HealthView, MeView } from "@/views/status";

import { axeViolations } from "../support/axe";
import * as fx from "../support/fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const P503: Problem = { status: 503, code: "storage_unavailable", title: "Storage unavailable", detail: "Retry later.", requestId: "req-9", retryAfterS: null };
const P403: Problem = { status: 403, code: "journey_forbidden", title: "Journey not allowed", detail: "Your token does not include this journey.", requestId: "req-8", retryAfterS: null };

async function expectAccessible(container: Element) {
  expect(await axeViolations(container)).toEqual([]);
}

describe("status views", () => {
  it("render health, components and token", async () => {
    const { container } = render(
      <>
        <HealthView result={ok(fx.health)} />
        <HealthDetailsView result={ok(fx.healthDetails)} />
        <MeView result={ok(fx.me)} />
      </>,
    );
    expect(screen.getByText("1.0.0")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Backend components" });
    expect(within(table).getByRole("row", { name: /reports unavailable storage_unavailable/ })).toBeInTheDocument();
    expect(screen.getByText("tok_0123456789ab")).toBeInTheDocument();
    await expectAccessible(container);
  });

  it("show problems per region", () => {
    render(
      <>
        <HealthView result={failed(P503)} />
        <HealthDetailsView result={ok(fx.healthDetails)} />
      </>,
    );
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByRole("table", { name: "Backend components" })).toBeInTheDocument();
  });
});

describe("journey views", () => {
  it("list journeys with links", async () => {
    const { container } = render(<JourneyListView result={ok(fx.journeys)} />);
    expect(screen.getByRole("link", { name: "user_onboarding" })).toHaveAttribute("href", "/journeys/user_onboarding");
    await expectAccessible(container);
  });

  it("have an empty list state", () => {
    render(<JourneyListView result={ok({ data: [], page: { limit: 200, next_cursor: null } })} />);
    expect(screen.getByRole("status")).toHaveTextContent("No journeys are visible to your token.");
  });

  it("render steps, metrics and friction", async () => {
    const { container } = render(
      <>
        <JourneyStepsView journey={fx.journey} />
        <MetricsView result={ok(fx.metrics)} />
        <FrictionView result={ok(fx.friction)} />
      </>,
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByText("30.5%")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Funnel" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Friction score per step/ })).toBeInTheDocument();
    await expectAccessible(container);
  });

  it("show 403 without retry and 503 with retry", () => {
    render(
      <>
        <MetricsView result={failed(P403)} />
        <FrictionView result={failed(P503)} />
      </>,
    );
    const [forbidden, unavailable] = screen.getAllByRole("alert");
    expect(forbidden).toHaveTextContent("Journey metrics: Not allowed for your token");
    expect(within(forbidden as HTMLElement).queryByRole("button")).toBeNull();
    expect(unavailable).toHaveTextContent("Friction summary: Storage unavailable");
    expect(within(unavailable as HTMLElement).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("have an empty metrics state", () => {
    render(<MetricsView result={ok({ ...fx.metrics, steps: [], funnel: [] })} />);
    expect(screen.getByRole("status")).toHaveTextContent("No events in this window (last 30 days).");
  });
});

describe("run views", () => {
  it("list runs with status and report links", async () => {
    const { container } = render(<RunListView result={ok(fx.runs)} status={undefined} />);
    const table = screen.getByRole("table", { name: "Runs, most recently updated first" });
    expect(within(table).getByText("completed")).toBeInTheDocument();
    expect(within(table).getByText("awaiting approval")).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: /Open report/ })).toHaveAttribute("href", `/reports/${fx.REPORT_ID}`);
    await expectAccessible(container);
  });

  it("have a filtered empty state", () => {
    render(<RunListView result={ok({ data: [], page: { limit: 50, next_cursor: null } })} status="failed" />);
    expect(screen.getByRole("status")).toHaveTextContent("No runs with status “failed”.");
  });

  it("label the status filter", async () => {
    const { container } = render(<RunFilter status="completed" />);
    expect(screen.getByRole("combobox", { name: "Status" })).toHaveValue("completed");
    await expectAccessible(container);
  });

  it("accept only known statuses from the query", () => {
    expect(parseStatus("failed")).toBe("failed");
    expect(parseStatus("nope")).toBeUndefined();
    expect(parseStatus(["failed"])).toBeUndefined();
  });

  it("render a run with steps and report", async () => {
    const { container } = render(<RunDetailView result={ok(fx.run)} />);
    expect(screen.getByRole("table", { name: "Workflow steps of this run" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open report (new tab)" })).toHaveAttribute("href", `/reports/${fx.REPORT_ID}`);
    await expectAccessible(container);
  });

  it("render a failed run's failure", () => {
    render(<RunDetailView result={ok(fx.failedRun)} />);
    expect(screen.getByRole("heading", { name: "Failure in data_worker" })).toBeInTheDocument();
    expect(screen.getByText("not written yet")).toBeInTheDocument();
  });

  it("show a run problem with a way back", () => {
    render(<RunDetailView result={failed({ ...P503, status: 404, code: "run_not_found", title: "Run not found" })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Run: Not found");
    expect(screen.getByRole("link", { name: "Back to runs" })).toBeInTheDocument();
  });
});
