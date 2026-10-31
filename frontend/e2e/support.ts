/** Shared helpers for the feature specs (Spec 14, design §5). */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { FIXTURE_API_PORT } from "../playwright.config";
import { startFixtureApi, type FixtureApi } from "./fixture-api";

export const LIVE = Boolean(process.env.E2E_LIVE_API_URL);
export const JOURNEY = "user_onboarding";

/** Starts the fixture API for the spec file (fixture mode) and returns a getter for it. */
export function fixtureApiForFile(): () => FixtureApi {
  let api: FixtureApi | null = null;
  test.beforeAll(async () => {
    api = await startFixtureApi(FIXTURE_API_PORT);
  });
  test.afterAll(async () => {
    await api?.close();
  });
  return () => {
    if (!api) {
      throw new Error("fixture API not started");
    }
    return api;
  };
}

export async function signIn(page: Page, token: string, next = "/"): Promise<void> {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("API token").fill(token);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
}

export async function expectAccessible(page: Page, label: string): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.help}`), `axe on ${label}`).toEqual([]);
}

/** The page's alerts without Next.js' route announcer (which also has role="alert"). */
export function alerts(page: Page) {
  return page.locator('[role="alert"]:not([id="__next-route-announcer__"])');
}

/** Console errors of a page (CSP violations, hydration errors), collected for a final assertion. */
export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(`${message.text()} (${message.location().url || "no url"})`);
    }
  });
  return errors;
}
