/**
 * The browser smoke test (Spec 13, OD-138): authentication boundary, every view of the slice, a visible and
 * recoverable API error, accessibility and cookie safety, against the production build.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { FIXTURE_API_PORT } from "../playwright.config";
import { FIXTURE_TOKEN, startFixtureApi, type FixtureApi } from "./fixture-api";

const LIVE = Boolean(process.env.E2E_LIVE_API_URL);
const TOKEN = LIVE ? (process.env.E2E_LIVE_TOKEN ?? "") : FIXTURE_TOKEN;
const JOURNEY = "user_onboarding";

let api: FixtureApi | null = null;

test.beforeAll(async () => {
  if (!LIVE) {
    api = await startFixtureApi(FIXTURE_API_PORT);
  }
});

test.afterAll(async () => {
  await api?.close();
});

async function expectAccessible(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.help}`), `axe on ${label}`).toEqual([]);
}

test("CJI frontend smoke test", async ({ page, context, request }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(`${message.text()} (${message.location().url || "no url"})`);
    }
  });

  await test.step("protected pages redirect to the login page without a session", async () => {
    for (const path of ["/", "/journeys", `/journeys/${JOURNEY}`, "/runs", "/reports/anything"]) {
      const response = await request.get(path, { maxRedirects: 0 });
      expect(response.status(), path).toBe(307);
      expect(response.headers().location ?? "", path).toContain("/login");
    }
    await page.goto("/journeys");
    await expect(page).toHaveURL(/\/login\?next=%2Fjourneys$/);
    await expect(page.getByRole("heading", { level: 1, name: "Customer Journey Intelligence" })).toBeVisible();
    if (api) {
      expect(api.requests.filter((r) => r.authenticated), "authenticated API calls before sign-in").toEqual([]);
    }
    await expectAccessible(page, "login");
  });

  await test.step("a wrong token is refused with a visible message", async () => {
    await page.getByLabel("API token").fill("cji_api_this-token-does-not-exist-000000");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("This token is not valid, has expired or was revoked.")).toBeVisible();
    await expect(page.getByLabel("API token")).toHaveAttribute("aria-invalid", "true");
    expect((await context.cookies()).find((c) => c.name === "cji_session")).toBeUndefined();
  });

  await test.step("sign in returns to the requested page; the session cookie is not readable by scripts", async () => {
    await page.getByLabel("API token").fill(TOKEN);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/journeys$/);
    const cookie = (await context.cookies()).find((c) => c.name === "cji_session");
    expect(cookie?.httpOnly).toBe(true);
    expect(cookie?.secure).toBe(true);
    expect(cookie?.sameSite).toBe("Strict");
    expect(cookie?.value).not.toContain(TOKEN);
    expect(await page.evaluate(() => document.cookie)).not.toContain("cji_session");
    expect(await page.content()).not.toContain(TOKEN);
  });

  await test.step("journey list and detail with the friction summary", async () => {
    const table = page.getByRole("table", { name: "Journeys visible to your token" });
    await expect(table).toBeVisible();
    await table.getByRole("link", { name: JOURNEY }).click();
    await expect(page.getByRole("heading", { level: 1, name: `Journey ${JOURNEY}` })).toBeVisible();
    await expect(page.getByRole("table", { name: "Funnel" })).toBeVisible();
    await expect(page.getByRole("table", { name: /Friction score per step/ })).toBeVisible();
    await expect(page.getByText(/Critical steps \(score at or above \d+\)/)).toBeVisible();
    await expectAccessible(page, "journey detail");
  });

  // Fault injection needs the fixture API; against a live cji-api this step is left out (test.skip here would
  // skip the whole test).
  if (api) {
  await test.step("an API error is visible with its request id and recovers with Retry", async () => {
    api?.failNextFriction(1);
    await page.reload();
    const alert = page.getByRole("alert").filter({ hasText: "Friction summary: Storage unavailable" });
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("storage_unavailable");
    await expect(alert).toContainText("req-fixture-0001");
    await expect(page.getByRole("table", { name: "Funnel" })).toBeVisible(); // other regions still render
    await alert.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByRole("table", { name: /Friction score per step/ })).toBeVisible();
    await expect(alert).toBeHidden();
  });
  } else {
    test.info().annotations.push({ type: "live", description: "fault-injection step left out (live cji-api)" });
  }

  await test.step("status page", async () => {
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Status" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Status" })).toBeVisible();
    await expect(page.getByRole("table", { name: "Backend components" })).toBeVisible();
    await expect(page.getByText("API version")).toBeVisible();
  });

  await test.step("workflow runs and report status", async () => {
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Runs" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Workflow runs" })).toBeVisible();
    const runs = page.getByRole("table", { name: "Runs, most recently updated first" });
    await expect(runs).toBeVisible();
    const withReport = runs.getByRole("row").filter({ has: page.getByRole("link", { name: /Open report/ }) }).first();
    if ((await withReport.count()) > 0) {
      const href = await withReport.getByRole("link", { name: /Open report/ }).getAttribute("href");
      const report = await page.request.get(href ?? "");
      expect(report.status()).toBe(200);
      expect(report.headers()["content-type"]).toContain("text/html");
      expect(report.headers()["content-security-policy"]).toContain("sandbox");
      await withReport.getByRole("rowheader").getByRole("link").click();
      await expect(page.getByRole("table", { name: "Workflow steps of this run" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Open report (new tab)" })).toBeVisible();
    }
  });

  await test.step("sign out ends the session", async () => {
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);
    expect((await context.cookies()).find((c) => c.name === "cji_session")).toBeUndefined();
    await page.goto("/runs");
    await expect(page).toHaveURL(/\/login\?next=%2Fruns$/);
  });

  await test.step("no console errors (CSP, hydration)", async () => {
    expect(consoleErrors).toEqual([]);
  });

  if (api) {
    expect(api.requests.every((r) => r.requestId), "X-Request-ID on every API call").toBe(true);
  }
});
