/**
 * Approval and resume (Spec 14, R6): one effect per submit (the idempotency key is reused), progress until the run
 * stops, and the resume path for a failed run.
 */
import { expect, test } from "@playwright/test";

import * as fx from "../tests/support/fixtures";
import { FIXTURE_OPERATOR_TOKEN } from "./fixture-api";
import { collectConsoleErrors, LIVE, signIn, fixtureApiForFile } from "./support";

test.skip(LIVE, "fixture API only");
const api = fixtureApiForFile();

test("approve a paused run and follow it to completion", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await signIn(page, FIXTURE_OPERATOR_TOKEN, `/runs/${fx.AWAITING_ID}`);
  const button = page.getByRole("button", { name: "Approve run" });
  await expect(button).toBeEnabled();
  await button.dblclick();
  await expect(page).toHaveURL(/\?approved=1$/);
  await expect(page.getByText("The run was approved.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Download report" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("completed").first()).toBeVisible();

  const approvals = api().requests.filter((r) => r.method === "POST" && r.path.endsWith("/approval"));
  expect(approvals.length).toBeGreaterThanOrEqual(1);
  expect(new Set(approvals.map((r) => r.idempotencyKey)).size).toBe(1);
  expect(errors).toEqual([]);
});

test("resume a failed run", async ({ page }) => {
  await signIn(page, FIXTURE_OPERATOR_TOKEN, `/runs/${fx.FAILED_ID}`);
  await expect(page.getByRole("heading", { name: "Failure in data_worker" })).toBeVisible();
  await page.getByRole("button", { name: "Resume run" }).click();
  await expect(page).toHaveURL(/\?resumed=1$/);
  await expect(page.getByRole("link", { name: "Download report" })).toBeVisible({ timeout: 20_000 });
  expect(api().requests.filter((r) => r.method === "POST" && r.path.endsWith("/resume"))).toHaveLength(1);
});

test("a conflict is shown next to the action", async ({ page }) => {
  // The first test approved AWAITING_ID; start a fresh run to get a paused one.
  await signIn(page, FIXTURE_OPERATOR_TOKEN, "/runs/new");
  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page.getByRole("heading", { name: "Approval" })).toBeVisible({ timeout: 20_000 });
  const runPath = new URL(page.url()).pathname;
  api().failNext("POST", `/api/v1${runPath}/approval`, {
    status: 409, code: "run_busy", title: "Run is busy", detail: "Another process is working on this run; retry later.",
  });
  await page.getByRole("button", { name: "Approve run" }).click();
  const alert = page.getByRole("alert").filter({ hasText: "Approve run" });
  await expect(alert).toContainText("Another process is working on this run");
  await expect(alert).toContainText("run_busy");
  await expect(page.getByRole("button", { name: "Approve run" })).toBeEnabled();
});
