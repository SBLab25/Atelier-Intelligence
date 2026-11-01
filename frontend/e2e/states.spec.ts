/**
 * Error, empty and permission states (Spec 14, R8, design §6): viewer permission texts, API problems with retry,
 * rate limits, not found and an expired session.
 */
import { expect, test } from "@playwright/test";

import * as fx from "../tests/support/fixtures";
import { FIXTURE_TOKEN } from "./fixture-api";
import { alerts, expectAccessible, JOURNEY, LIVE, signIn, fixtureApiForFile } from "./support";

test.skip(LIVE, "fixture API only");
const api = fixtureApiForFile();

test("viewers see disabled actions with the reason", async ({ page }) => {
  await signIn(page, FIXTURE_TOKEN, "/runs/new");
  const start = page.getByRole("button", { name: "Start run" });
  await expect(start).toBeDisabled();
  await expect(page.getByText(/Requires the operator role/).first()).toBeVisible();
  await expectAccessible(page, "start run (viewer)");

  await page.goto(`/runs/${fx.AWAITING_ID}`);
  await expect(page.getByRole("button", { name: "Approve run" })).toBeDisabled();
  await page.goto("/ingest");
  await expect(page.getByText(/Requires the operator role/)).toBeVisible();
  await expect(page.getByLabel("Event file")).toHaveCount(0);
  expect(api().requests.filter((r) => r.method === "POST")).toHaveLength(0);
});

test("a 503 on run results is shown and recovers with Retry", async ({ page }) => {
  await signIn(page, FIXTURE_TOKEN, "/runs");
  api().failNext("GET", `/api/v1/runs/${fx.RUN_ID}/results`, {
    status: 503, code: "storage_unavailable", title: "Storage unavailable", detail: "A storage backend is unavailable; retry later.",
  });
  await page.goto(`/runs/${fx.RUN_ID}`);
  const alert = page.getByRole("alert").filter({ hasText: "Run results: Storage unavailable" });
  await expect(alert).toContainText("req-fixture-0001");
  await expect(alert).toContainText("Try again in 2 seconds.");
  await expect(page.getByRole("table", { name: "Workflow steps of this run" })).toBeVisible();
  await alert.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("heading", { name: "Executive narrative" })).toBeVisible();
  await expect(alert).toBeHidden();
});

test("a rate limit says how long to wait", async ({ page }) => {
  await signIn(page, FIXTURE_TOKEN, "/runs");
  api().failNext("GET", "/api/v1/reports", {
    status: 429, code: "rate_limited", title: "Too many requests", detail: "Too many requests; retry after the Retry-After interval.",
  });
  await page.goto("/reports");
  const alert = alerts(page);
  await expect(alert).toContainText("Reports: Too many requests");
  await expect(alert).toContainText("Try again in 2 seconds.");
});

test("not found and empty states", async ({ page }) => {
  await signIn(page, FIXTURE_TOKEN, "/runs");
  await page.goto("/runs/no-such-run");
  await expect(alerts(page)).toContainText("Run: Not found");
  await expect(page.getByRole("link", { name: "Back to runs" })).toBeVisible();
  await page.goto(`/journeys/${JOURNEY}/steps/not_a_step`);
  await expect(page.getByText("This step is not one of the journey's configured steps.")).toBeVisible();
  await expect(page.getByText("No metrics for this step in the selected window.")).toBeVisible();
  await expect(page.getByText("No friction score for this step in the selected window.")).toBeVisible();
});

test("an expired token ends the session", async ({ page, context }) => {
  await signIn(page, FIXTURE_TOKEN, "/runs");
  api().failNext("GET", "/api/v1/runs", {
    status: 401, code: "invalid_token", title: "Invalid token", detail: "The token is unknown, revoked or expired.",
  });
  await page.goto("/runs");
  await expect(page).toHaveURL(/\/login/);
  expect((await context.cookies()).find((c) => c.name === "cji_session")).toBeUndefined();
});
