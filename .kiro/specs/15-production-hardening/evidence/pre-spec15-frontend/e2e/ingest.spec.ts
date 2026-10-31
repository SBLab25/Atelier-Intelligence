/**
 * Ingestion with validation feedback (Spec 14, R2): upload, review the summary (nothing written), then append;
 * replacing needs the admin role and a confirmation.
 */
import { expect, test } from "@playwright/test";

import * as fx from "../tests/support/fixtures";
import { FIXTURE_ADMIN_TOKEN, FIXTURE_OPERATOR_TOKEN } from "./fixture-api";
import { alerts, collectConsoleErrors, expectAccessible, LIVE, signIn, fixtureApiForFile } from "./support";

test.skip(LIVE, "fixture API only");
const api = fixtureApiForFile();

const FILE = {
  name: "events.json",
  mimeType: "application/json",
  buffer: Buffer.from(JSON.stringify([{ user_id: "u1", step_id: "landing_page", event_type: "page_view" }])),
};

test("validate, review and append an event file", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await signIn(page, FIXTURE_OPERATOR_TOKEN, "/ingest");
  await expectAccessible(page, "ingest");
  await page.getByLabel("Event file").setInputFiles(FILE);
  await page.getByLabel(/Column mapping/).fill("userId=user_id");
  await page.getByRole("button", { name: "Validate file" }).click();

  await expect(page.getByRole("heading", { name: "Validation of events.json" })).toBeVisible();
  await expect(page.getByText("Nothing has been written yet.")).toBeVisible();
  await expect(page.getByRole("table", { name: "Steps found in the file" })).toContainText("unknown_step");
  await expect(page.getByText(/Journey steps without any row in this file: payment_info/)).toBeVisible();
  await expectAccessible(page, "validation summary");
  const validate = api().requests.find((r) => r.path.startsWith("/api/v1/ingestions/validations"));
  expect(validate?.path).toContain("filename=events.json");
  expect(validate?.path).toContain("map=userId%3Duser_id");
  expect(validate?.contentType).toBe("application/json");
  expect(validate?.bodyBytes).toBe(FILE.buffer.length);
  expect(api().requests.filter((r) => r.path === "/api/v1/ingestions")).toHaveLength(0);

  await expect(page.getByLabel(/Replace: delete every stored event/)).toBeDisabled();
  await page.getByRole("button", { name: `Write ${fx.validation.rows.accepted} rows` }).click();
  await expect(page.getByRole("heading", { name: "Events written" })).toBeVisible();
  await expect(page.getByText(/3 rows written to tracking_events \(append\)/)).toBeVisible();
  const writes = api().requests.filter((r) => r.method === "POST" && r.path === "/api/v1/ingestions");
  expect(writes).toHaveLength(1);
  expect(writes[0]?.idempotencyKey).toBeTruthy();
  expect(errors).toEqual([]);
});

test("replace needs the confirmation", async ({ page }) => {
  await signIn(page, FIXTURE_ADMIN_TOKEN, "/ingest");
  await page.getByLabel("Event file").setInputFiles(FILE);
  await page.getByRole("button", { name: "Validate file" }).click();
  await page.getByLabel(/Replace: delete every stored event/).check();
  await page.getByRole("button", { name: /Write 3 rows/ }).click();
  await expect(alerts(page)).toContainText("Tick the confirmation box");
  await page.getByLabel(/I understand that all stored events/).check();
  await page.getByRole("button", { name: /Write 3 rows/ }).click();
  await expect(page.getByText(/3 rows written to tracking_events \(replace\)/)).toBeVisible();
});

test("files of the wrong type are refused before upload", async ({ page }) => {
  await signIn(page, FIXTURE_OPERATOR_TOKEN, "/ingest");
  const before = api().requests.length;
  await page.getByLabel("Event file").setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("x") });
  await page.getByRole("button", { name: "Validate file" }).click();
  await expect(alerts(page)).toContainText("Only .json, .ndjson, .jsonl and .csv files");
  expect(api().requests.slice(before).filter((r) => r.path.startsWith("/api/v1/ingestions"))).toHaveLength(0);
});
