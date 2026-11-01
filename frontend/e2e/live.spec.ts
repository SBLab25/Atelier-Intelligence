/**
 * Live parity against a real cji-api (Spec 14, OD-154; gate live phase). Runs only with E2E_LIVE_API_URL,
 * E2E_LIVE_TOKEN (viewer) and E2E_LIVE_OPERATOR_TOKEN. Starts a real run (demo data, offline LLM: fallback outcomes),
 * approves it, checks provenance and the report download, validates a file without writing it, and compares what the
 * pages show with the API's JSON.
 */
import { expect, request as playwrightRequest, test, type APIRequestContext } from "@playwright/test";

import { count, pct } from "../src/lib/format";
import { collectConsoleErrors, expectAccessible, JOURNEY, signIn } from "./support";

const API_URL = process.env.E2E_LIVE_API_URL ?? "";
const VIEWER = process.env.E2E_LIVE_TOKEN ?? "";
const OPERATOR = process.env.E2E_LIVE_OPERATOR_TOKEN ?? "";

test.skip(!API_URL || !VIEWER || !OPERATOR, "live mode only (E2E_LIVE_API_URL, E2E_LIVE_TOKEN, E2E_LIVE_OPERATOR_TOKEN)");
test.describe.configure({ mode: "serial" });

let api: APIRequestContext;
let runId = "";

test.beforeAll(async () => {
  api = await playwrightRequest.newContext({ baseURL: API_URL, extraHTTPHeaders: { Authorization: `Bearer ${OPERATOR}` } });
});

test.afterAll(async () => {
  await api.dispose();
});

async function runStatus(id: string): Promise<{ status: string; active: boolean }> {
  const response = await api.get(`/api/v1/runs/${id}`);
  expect(response.status()).toBe(200);
  return (await response.json()) as { status: string; active: boolean };
}

test("journey page shows the API's metrics unchanged", async ({ page }) => {
  const metrics = (await (await api.get(`/api/v1/journeys/${JOURNEY}/metrics?days=30`)).json()) as {
    funnel: { step_id: string; users: number; drop_off_pct: number }[];
    overall_completion_pct: number;
  };
  await signIn(page, VIEWER, `/journeys/${JOURNEY}?days=30`);
  await expect(page.getByText(`Overall completion: ${pct(metrics.overall_completion_pct)}`)).toBeVisible();
  const funnel = page.getByRole("table", { name: "Funnel" });
  for (const step of metrics.funnel) {
    const row = funnel.getByRole("row", { name: new RegExp(`^${step.step_id}\\b`) });
    await expect(row.getByRole("cell").nth(0)).toHaveText(count(step.users));
    await expect(row.getByRole("cell").nth(1)).toHaveText(pct(step.drop_off_pct));
  }
  await expectAccessible(page, "live journey");
});

test("an operator starts a run, approves it and gets a report with provenance", async ({ page }) => {
  test.setTimeout(900_000);
  const errors = collectConsoleErrors(page);
  await signIn(page, OPERATOR, "/runs/new");
  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]{36}\?started=1$/);
  runId = new URL(page.url()).pathname.split("/").pop() ?? "";

  await expect.poll(async () => (await runStatus(runId)).status, { timeout: 600_000, intervals: [2_000] }).toMatch(
    /awaiting_approval|failed/,
  );
  expect((await runStatus(runId)).status).toBe("awaiting_approval");
  await page.goto(`/runs/${runId}`);
  await page.getByRole("button", { name: "Approve run" }).click();
  await expect(page).toHaveURL(/\?approved=1$/);
  await expect.poll(async () => (await runStatus(runId)).status, { timeout: 600_000, intervals: [2_000] }).toMatch(
    /completed|failed/,
  );
  expect((await runStatus(runId)).status).toBe("completed");

  await page.goto(`/runs/${runId}`);
  await expect(page.getByRole("heading", { name: "Executive narrative" })).toBeVisible();
  const results = (await (await api.get(`/api/v1/runs/${runId}/results`)).json()) as {
    narrative_provenance: { source: string };
    insights: { provenance: { source: string } }[];
  };
  expect(results.narrative_provenance.source).not.toBe("not_recorded");
  for (const insight of results.insights) {
    expect(insight.provenance.source).not.toBe("not_recorded");
  }
  const expected = results.narrative_provenance.source === "llm" ? "Written by the language model" : "Fallback text";
  await expect(page.getByText(expected).first()).toBeVisible();

  const download = await page.request.get(
    (await page.getByRole("link", { name: "Download report" }).getAttribute("href")) ?? "",
  );
  expect(download.status()).toBe(200);
  expect(download.headers()["content-disposition"]).toMatch(/^attachment; filename="cji_report_.+\.html"$/);
  expect(errors).toEqual([]);
});

test("a file is validated against the real parser without writing", async ({ page }) => {
  await signIn(page, OPERATOR, "/ingest");
  const rows = [
    { user_id: "live-u1", step_id: "landing_page", event_type: "page_view", timestamp: "2026-01-01T00:00:00Z" },
    { user_id: "live-u2", step_id: "landing_page", event_type: "teleport", timestamp: "2026-01-01T00:00:00Z" },
  ];
  await page.getByLabel("Event file").setInputFiles({
    name: "live.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(rows)),
  });
  await page.getByRole("button", { name: "Validate file" }).click();
  await expect(page.getByRole("heading", { name: "Validation of live.json" })).toBeVisible();
  const summary = page.getByRole("region", { name: "Validation of live.json" });
  await expect(summary).toContainText("Rows that would be written");
  await expect(summary.getByRole("definition").nth(1)).toHaveText("1");
  await expect(summary.getByRole("definition").nth(2)).toHaveText("1");
});

test("viewers get the permission states on the live API", async ({ page }) => {
  await signIn(page, VIEWER, `/journeys/${JOURNEY}/steps/landing_page`);
  await expect(page.getByText(/Events are only listed for operators/)).toBeVisible();
  await page.goto("/runs/new");
  await expect(page.getByRole("button", { name: "Start run" })).toBeDisabled();
});
