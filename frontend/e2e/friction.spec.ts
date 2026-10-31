/**
 * Friction drill-down (Spec 14, R4): from the friction table to one step's metrics, score, insight and events; viewers
 * see the permission state instead of events.
 */
import { expect, test } from "@playwright/test";

import * as fx from "../tests/support/fixtures";
import { FIXTURE_OPERATOR_TOKEN, FIXTURE_TOKEN } from "./fixture-api";
import { collectConsoleErrors, expectAccessible, JOURNEY, LIVE, signIn, fixtureApiForFile } from "./support";

test.skip(LIVE, "fixture API only");
const api = fixtureApiForFile();
const STEP = "payment_info";

test("operators drill into a step and page through its events", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await signIn(page, FIXTURE_OPERATOR_TOKEN, `/journeys/${JOURNEY}`);
  await page.getByRole("table", { name: /Friction score per step/ }).getByRole("link", { name: STEP }).click();
  await expect(page.getByRole("heading", { level: 1, name: new RegExp(`Step ${STEP}`) })).toBeVisible();

  const score = fx.friction.scores.find((s) => s.step_id === STEP);
  await expect(page.getByText(`${score?.score}`, { exact: true })).toBeVisible();
  await expect(page.getByText("high_drop_off, rage_clicks")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Card form rejects valid input" })).toBeVisible();

  const events = page.getByRole("table", { name: "Events of this step, newest first" });
  await expect(events.getByRole("row")).toHaveCount(fx.events.data.length + 1);
  expect(api().requests.some((r) => r.path.includes(`/events?`) && r.path.includes(`step_id=${STEP}`))).toBe(true);
  await expectAccessible(page, "step detail");

  await page.getByLabel("Event type").fill("error");
  await page.getByRole("button", { name: "Filter events" }).click();
  await expect(page).toHaveURL(/event_type=error/);
  await expect(page.getByRole("table", { name: "Events of this step, newest first" })).toBeVisible();
  expect(api().requests.some((r) => r.path.includes("event_type=error"))).toBe(true);

  await page.getByRole("link", { name: "Older events" }).click();
  await expect(page.getByText("End of the list.")).toBeVisible();
  expect(api().requests.some((r) => r.path.includes("cursor="))).toBe(true);
  expect(errors).toEqual([]);
});

test("viewers see the permission state instead of events", async ({ page }) => {
  await signIn(page, FIXTURE_TOKEN, `/journeys/${JOURNEY}/steps/${STEP}`);
  await expect(page.getByText(/Events are only listed for operators/)).toBeVisible();
  await expect(page.getByRole("table", { name: "Events of this step, newest first" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Card form rejects valid input" })).toBeVisible();
});
