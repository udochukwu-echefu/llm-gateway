import { test as base, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { responseScanner } from "./no-leak";

interface Credentials {
  platform: string;
  orgKey: string;
  revocable: string;
  org: string;
  other: string;
}
interface LeakTotals {
  responses: number;
  permittedResponses: number;
  tenantKeys: string[];
  permitted: Map<string, string>;
}
interface Fixtures {
  credentials: Credentials;
  coverage: void;
  recordKey: (key: string, permitCreation?: boolean) => void;
}

export const test = base.extend<Fixtures, { leaks: LeakTotals }>({
  credentials: async ({}, provide) => {
    const state = readFileSync(resolve("tests/e2e/.state.json"), "utf8");
    await provide(JSON.parse(state));
  },
  leaks: [async ({}, provide) => {
    const totals: LeakTotals = {
      responses: 0, permittedResponses: 0, tenantKeys: [], permitted: new Map(),
    };
    await provide(totals);
    expect(totals.permittedResponses, "Exactly one permitted key-creation response")
      .toBe(totals.permitted.size ? 1 : 0);
    console.log(`No-leak scan total: ${totals.responses} browser responses; `
      + `${totals.permittedResponses} permitted key-creation response; zero leaks.`);
  }, { scope: "worker" }],
  recordKey: async ({ leaks }, provide, info) => {
    await provide((key, permitCreation = false) => {
      leaks.tenantKeys.push(key);
      if (permitCreation) leaks.permitted.set(info.testId, key);
    });
  },
  coverage: [async ({ page, credentials, leaks }, provide, info) => {
    const scanner = await responseScanner(page);
    await provide();
    const result = await scanner.verify(
      [credentials.platform, credentials.orgKey, credentials.revocable],
      leaks.tenantKeys, leaks.permitted.get(info.testId),
    );
    leaks.responses += result.responses;
    leaks.permittedResponses += result.permitted;
  }, { auto: true }],
});

export { expect };

export async function signIn(page: Page, key: string) {
  await page.goto("/login");
  await page.getByLabel("Admin API key").fill(key);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
}

export async function screenshot(page: Page, name: string) {
  if (process.env.CONSOLE_SCREENSHOTS !== "1") return;
  const images = resolve("../docs/images");
  mkdirSync(images, { recursive: true });
  await page.screenshot({ path: resolve(images, `console-${name}.png`), fullPage: true });
}
