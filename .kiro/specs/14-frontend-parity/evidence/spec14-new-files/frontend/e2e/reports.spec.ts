/** Report preview and download (Spec 14, R7). */
import { expect, test } from "@playwright/test";

import * as fx from "../tests/support/fixtures";
import { FIXTURE_TOKEN } from "./fixture-api";
import { expectAccessible, LIVE, signIn, fixtureApiForFile } from "./support";

test.skip(LIVE, "fixture API only");
const api = fixtureApiForFile();

test("list, preview in a sandbox and download a report", async ({ page }) => {
  await signIn(page, FIXTURE_TOKEN, "/reports");
  const table = page.getByRole("table", { name: "Reports, newest first" });
  await expect(table.getByRole("row")).toHaveCount(fx.reports.data.length + 1);
  await expectAccessible(page, "reports");

  const preview = await page.request.get(`/reports/${fx.REPORT_ID}`);
  expect(preview.status()).toBe(200);
  expect(preview.headers()["content-security-policy"]).toContain("sandbox");
  expect(preview.headers()["content-disposition"]).toBe("inline");

  const download = page.waitForEvent("download");
  await table.getByRole("link", { name: /Download/ }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe(`cji_report_${fx.REPORT_ID}.html`);

  const direct = await page.request.get(`/reports/${fx.REPORT_ID}/download`);
  expect(direct.headers()["content-disposition"]).toBe(`attachment; filename="cji_report_${fx.REPORT_ID}.html"`);
  expect(direct.headers()["content-security-policy"]).toContain("sandbox");
  expect(api().requests.some((r) => r.path.endsWith("/content?disposition=attachment"))).toBe(true);
});

test("an unknown report shows the API's problem", async ({ page }) => {
  await signIn(page, FIXTURE_TOKEN, "/reports");
  const response = await page.request.get("/reports/does_not_exist/download");
  expect(response.status()).toBe(404);
  expect(await response.text()).toContain("not_found");
});
