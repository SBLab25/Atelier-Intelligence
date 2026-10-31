/**
 * AI insight generation and provenance (Spec 14, R5): an operator starts a run from the browser, the page follows it
 * until it pauses for approval, and each insight and the narrative say where they came from.
 */
import { expect, test } from "@playwright/test";

import * as fx from "../tests/support/fixtures";
import { FIXTURE_OPERATOR_TOKEN } from "./fixture-api";
import { collectConsoleErrors, expectAccessible, LIVE, signIn, fixtureApiForFile } from "./support";

test.skip(LIVE, "fixture API only");
const api = fixtureApiForFile();

test("start a run and follow it to the approval step", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await signIn(page, FIXTURE_OPERATOR_TOKEN, "/runs");
  await page.getByRole("link", { name: "Start a run" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Start a run" })).toBeVisible();
  await expectAccessible(page, "start run");
  await page.getByLabel(/Window in days/).fill("14");
  await page.getByRole("button", { name: "Start run" }).click();

  await expect(page).toHaveURL(/\/runs\/00000000-0000-4000-8000-\d{12}\?started=1$/);
  await expect(page.getByText("The run was started.")).toBeVisible();
  await expect(page.getByText("This page updates every 5 seconds")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Approval" })).toBeVisible({ timeout: 20_000 });

  const start = api().requests.filter((r) => r.method === "POST" && r.path === "/api/v1/runs");
  expect(start).toHaveLength(1);
  expect(start[0]?.idempotencyKey).toMatch(/^[A-Za-z0-9._-]{8,64}$/);
  expect(errors).toEqual([]);
});

test("insights and narrative show their provenance and the usage totals", async ({ page }) => {
  await signIn(page, FIXTURE_OPERATOR_TOKEN, `/runs/${fx.RUN_ID}`);
  await expect(page.getByRole("heading", { name: "Executive narrative" })).toBeVisible();
  await expect(page.getByText(fx.runResults.narrative ?? "")).toBeVisible();
  await expect(page.getByText("Written by the language model (openai/gpt-oss-120b, groq)").first()).toBeVisible();
  const cards = page.locator("article.insight");
  await expect(cards).toHaveCount(3);
  await expect(cards.nth(1)).toContainText("Fallback text, not written by the language model (reason: llm_disabled)");
  await expect(cards.nth(2)).toContainText("Provenance not recorded");
  await expect(page.getByRole("table", { name: /Prioritized fixes/ })).toBeVisible();
  await expect(page.getByText("1,200")).toBeVisible();
  await expectAccessible(page, "run results");
});
