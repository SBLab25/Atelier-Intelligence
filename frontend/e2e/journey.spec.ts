/**
 * Journey and funnel analytics (Spec 14, R3): the page shows the API's funnel and step metrics unchanged (only the
 * documented display rounding, requirements §4), and the window selector reaches the API.
 */
import { expect, test } from "@playwright/test";

import { pct, count } from "../src/lib/format";
import * as fx from "../tests/support/fixtures";
import { FIXTURE_TOKEN } from "./fixture-api";
import { collectConsoleErrors, expectAccessible, JOURNEY, LIVE, signIn, fixtureApiForFile } from "./support";

test.skip(LIVE, "fixture API only (live parity runs in live.spec.ts)");
const api = fixtureApiForFile();

test("funnel and step metrics match the API values", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await signIn(page, FIXTURE_TOKEN, `/journeys/${JOURNEY}`);
  await expect(page.getByRole("heading", { level: 1, name: `Journey ${JOURNEY}` })).toBeVisible();

  const funnel = page.getByRole("table", { name: "Funnel" });
  for (const step of fx.metrics.funnel) {
    const row = funnel.getByRole("row", { name: new RegExp(`^${step.step_id}\\b`) });
    await expect(row.getByRole("cell").nth(0)).toHaveText(count(step.users));
    await expect(row.getByRole("cell").nth(1)).toHaveText(pct(step.drop_off_pct));
  }
  await expect(page.getByText(`Overall completion: ${pct(fx.metrics.overall_completion_pct)}`)).toBeVisible();

  const metrics = page.getByRole("table", { name: "Step metrics" });
  const first = fx.metrics.steps[0];
  if (!first) {
    throw new Error("fixture without steps");
  }
  const row = metrics.getByRole("row", { name: new RegExp(`^${first.step_id}`) });
  await expect(row.getByRole("cell").nth(0)).toHaveText(count(first.unique_users));
  await expect(row.getByRole("cell").nth(1)).toHaveText(pct(first.completion_rate_pct));
  await expect(row.getByRole("cell").nth(4)).toHaveText("5.2 s");
  await expectAccessible(page, "journey detail");

  await page.getByLabel("Analysis window").selectOption("7");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/days=7/);
  await expect(page.getByText(/^Overall completion: .*\(last 7 days\)$/)).toBeVisible();
  expect(api().requests.some((r) => r.path.startsWith(`/api/v1/journeys/${JOURNEY}/metrics?days=7`))).toBe(true);
  expect(api().requests.some((r) => r.path.startsWith(`/api/v1/journeys/${JOURNEY}/friction?days=7`))).toBe(true);
  expect(errors).toEqual([]);
});
