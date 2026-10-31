import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { FrictionSummary } from "@/components/FrictionSummary";
import { isCurrent, Nav } from "@/components/Nav";
import { describeProblem, ProblemPanel } from "@/components/ProblemPanel";
import { EmptyState, Loading, StatusBadge, Timestamp } from "@/components/States";
import type { Problem } from "@/lib/api/problem";

import { axeViolations } from "../support/axe";
import { friction } from "../support/fixtures";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }), usePathname: () => "/journeys/user_onboarding" }));

const PROBLEM: Problem = {
  status: 503,
  code: "storage_unavailable",
  title: "Storage unavailable",
  detail: "A storage backend is unavailable; retry later.",
  requestId: "req-123",
  retryAfterS: null,
};

describe("ProblemPanel", () => {
  it("shows the problem with code and request id and retries", async () => {
    const { container } = render(<ProblemPanel problem={PROBLEM} what="Friction summary" />);
    const alert = screen.getByRole("alert");
    expect(within(alert).getByRole("heading", { name: "Friction summary: Storage unavailable" })).toBeInTheDocument();
    expect(alert).toHaveTextContent("A storage backend is unavailable; retry later.");
    expect(alert).toHaveTextContent("storage_unavailable");
    expect(alert).toHaveTextContent("req-123");
    await userEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("shows the Retry-After wait for 429", () => {
    render(<ProblemPanel problem={{ ...PROBLEM, status: 429, code: "rate_limited", retryAfterS: 30 }} what="Runs" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Try again in 30 seconds.");
  });

  it.each([
    [403, "Not allowed for your token", false],
    [404, "Not found", false],
    [422, "The request was not accepted", false],
    [429, "Too many requests", true],
    [500, "Storage unavailable", true],
  ])("describes %i", (status, heading, retry) => {
    expect(describeProblem({ ...PROBLEM, status })).toEqual({ heading, retry });
  });

  it("offers a way back instead of retry for 404", () => {
    render(<ProblemPanel problem={{ ...PROBLEM, status: 404 }} what="Run" back={{ href: "/runs", label: "Back to runs" }} />);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.getByRole("link", { name: "Back to runs" })).toHaveAttribute("href", "/runs");
  });
});

describe("FrictionSummary", () => {
  it("renders the API's scores and critical flags as given (OD-140)", async () => {
    const { container } = render(<FrictionSummary friction={friction} />);
    const table = screen.getByRole("table", { name: "Friction score per step (threshold 60)" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getByRole("rowheader").textContent)).toEqual(["payment_info", "landing_page"]);
    expect(within(rows[0] as HTMLElement).getAllByRole("cell").map((c) => c.textContent)).toEqual([
      "78", "Yes", "high_drop_off, rage_clicks", "0.9",
    ]);
    expect(within(rows[1] as HTMLElement).getAllByRole("cell")[1]).toHaveTextContent("No");
    expect(screen.getByText("payment_info", { selector: "strong" })).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("does not re-threshold: a high score the API did not flag stays not critical", () => {
    const unflagged = { ...friction, critical_steps: [], scores: friction.scores.map((s) => ({ ...s, is_critical: false })) };
    render(<FrictionSummary friction={unflagged} />);
    expect(screen.getByText(/Critical steps/)).toHaveTextContent("none");
    expect(screen.queryByText("Yes")).toBeNull();
  });

  it("has an empty state", () => {
    render(<FrictionSummary friction={{ ...friction, scores: [], critical_steps: [] }} />);
    expect(screen.getByRole("status")).toHaveTextContent("No friction scores for this window");
  });
});

describe("small components", () => {
  it("announce loading and empty states", async () => {
    const { container } = render(
      <>
        <Loading label="Loading runs…" />
        <EmptyState>No runs yet.</EmptyState>
      </>,
    );
    expect(screen.getAllByRole("status")[0]).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("No runs yet.")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("show status as text", () => {
    render(<StatusBadge status="awaiting_approval" />);
    expect(screen.getByText("awaiting approval")).toBeInTheDocument();
  });

  it("format timestamps in UTC", () => {
    render(<Timestamp value="2026-10-28T23:52:30+02:00" />);
    expect(screen.getByText("2026-10-28 21:52:30 UTC")).toHaveAttribute("datetime", "2026-10-28T21:52:30.000Z");
  });

  it("mark the current navigation item", async () => {
    const { container } = render(<Nav />);
    expect(screen.getByRole("link", { name: "Journeys" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
    expect(isCurrent("/", "/")).toBe(true);
    expect(isCurrent("/runs", "/")).toBe(false);
    expect(await axeViolations(container)).toEqual([]);
  });
});
