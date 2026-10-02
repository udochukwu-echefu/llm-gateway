import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Page } from "@playwright/test";
import { expect } from "./fixtures";
import data from "./calendar-data.json";

export async function openCalendar(page: Page) {
  const trigger = page.getByRole("button", { name: "Open start date calendar" });
  await trigger.click();
  const calendar = page.getByRole("dialog", { name: "Date range", exact: true });
  await expect(calendar).toBeVisible();
  return calendar;
}

export async function chooseCalendarPreset(page: Page, preset: string) {
  const calendar = await openCalendar(page);
  await calendar.getByRole("button", { name: preset, exact: true }).click();
  await calendar.getByRole("button", { name: "Apply", exact: true }).click();
  await expect(page.getByRole("button", { name: "Open start date calendar" })).toBeFocused();
}

export async function submitCalendarFilters(page: Page, endpoint: string) {
  const response = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      url.pathname.startsWith("/api/admin/") &&
      url.pathname.endsWith(endpoint) &&
      url.searchParams.has("until")
    );
  });
  await page.getByRole("button", { name: "Apply filters" }).click();
  const result = await response;
  expect(result.status()).toBe(200);
  return { url: new URL(result.url()), body: await result.json() };
}

export async function expectBounds(page: Page, http: URL, since: string, until: string) {
  await expect.poll(() => new URL(page.url()).searchParams.get("until")).toBe(until);
  for (const [key, value] of Object.entries({ since, until })) {
    expect(new URL(page.url()).searchParams.get(key)).toBe(value);
    expect(http.searchParams.get(key)).toBe(value);
    await expect(page.locator(".filter-chips")).toContainText(value);
  }
}

export async function expectAttempts(page: Page, ids: string[]) {
  await expect(page.locator(".request-table tbody tr")).toHaveCount(ids.length);
  const visible = await page.locator(".request-table .row-detail").allTextContents();
  expect(visible.sort()).toEqual([...ids].sort());
}

export async function calendarEvidence(page: Page, name: string, evidence?: unknown) {
  const directory = process.env.CALENDAR_EVIDENCE_DIR;
  if (!directory) return;
  mkdirSync(directory, { recursive: true });
  if (evidence)
    writeFileSync(resolve(directory, `${name}.json`), JSON.stringify(evidence, null, 2));
  await settleCalendar(page);
  await page.screenshot({ path: resolve(directory, `${name}.png`), fullPage: false });
  if (name.startsWith("requests-")) {
    await page.locator(".request-table").scrollIntoViewIfNeeded();
    await page.screenshot({ path: resolve(directory, `${name}-results.png`), fullPage: false });
  }
}

export async function settleCalendar(page: Page) {
  await page.evaluate(async () => {
    const animations = document.getAnimations().filter((animation) => {
      const target = (animation.effect as KeyframeEffect | null)?.target;
      return (
        target instanceof Element &&
        !!target.closest(".date-range-popover") &&
        animation.effect?.getComputedTiming().iterations !== Infinity
      );
    });
    await Promise.all(animations.map((animation) => animation.finished.catch(() => {})));
  });
}

export const calendarData = data;
