import { test as base, expect, type Page, type BrowserContext } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { responseScanner } from "./no-leak";

interface Credentials {
  platform: string;
  demoPlatform: string;
  demoOrg: string;
  orgKey: string;
  revocable: string;
  viewer: string;
  orgViewer: string;
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
  extraScans: {
    scanners: Awaited<ReturnType<typeof responseScanner>>[];
    contexts: BrowserContext[];
  };
  newScannedPage: () => Promise<Page>;
  recordKey: (key: string, permitCreation?: boolean) => void;
}

export const test = base.extend<Fixtures, { leaks: LeakTotals }>({
  credentials: async ({}, provide) => {
    if (process.env.DEMO_APPLIANCE_E2E === "1") {
      // Actual boot keys never leave the appliance. The scanner also rejects all key patterns.
      const placeholder = "unissued-appliance-test-placeholder";
      await provide({
        platform: placeholder,
        demoPlatform: placeholder,
        demoOrg: placeholder,
        orgKey: placeholder,
        revocable: placeholder,
        viewer: placeholder,
        orgViewer: placeholder,
        org: "Demo Co",
        other: "Northwind Health",
      });
      return;
    }
    const state = readFileSync(resolve("tests/e2e/.state.json"), "utf8");
    await provide(JSON.parse(state));
  },
  leaks: [
    async ({}, provide) => {
      const totals: LeakTotals = {
        responses: 0,
        permittedResponses: 0,
        tenantKeys: [],
        permitted: new Map(),
      };
      await provide(totals);
      expect(totals.permittedResponses, "Exactly one permitted key-creation response").toBe(
        totals.permitted.size ? 1 : 0,
      );
      console.log(
        `No-leak scan total: ${totals.responses} browser responses; ` +
          `${totals.permittedResponses} permitted key-creation response; zero leaks.`,
      );
    },
    { scope: "worker" },
  ],
  recordKey: async ({ leaks }, provide, info) => {
    await provide((key, permitCreation = false) => {
      leaks.tenantKeys.push(key);
      if (permitCreation) leaks.permitted.set(info.testId, key);
    });
  },
  extraScans: async ({}, provide) => {
    await provide({ scanners: [], contexts: [] });
  },
  newScannedPage: async ({ browser, extraScans }, provide) => {
    await provide(async () => {
      const context = await browser.newContext({
        baseURL: `http://[::1]:${process.env.CONSOLE_TEST_PORT ?? "3100"}`,
        viewport: { width: 1440, height: 1050 },
      });
      const page = await context.newPage();
      extraScans.contexts.push(context);
      extraScans.scanners.push(await responseScanner(page));
      return page;
    });
  },
  coverage: [
    async ({ page, credentials, leaks, extraScans }, provide, info) => {
      const scanner = await responseScanner(page);
      await provide();
      const result = await scanner.verify(
        [
          credentials.platform,
          credentials.orgKey,
          credentials.revocable,
          credentials.demoPlatform,
          credentials.demoOrg,
          credentials.viewer,
          credentials.orgViewer,
        ],
        leaks.tenantKeys,
        leaks.permitted.get(info.testId),
      );
      leaks.responses += result.responses;
      leaks.permittedResponses += result.permitted;
      for (const scanner of extraScans.scanners) {
        const extra = await scanner.verify(
          [
            credentials.platform,
            credentials.orgKey,
            credentials.revocable,
            credentials.demoPlatform,
            credentials.demoOrg,
            credentials.viewer,
            credentials.orgViewer,
          ],
          leaks.tenantKeys,
        );
        leaks.responses += extra.responses;
      }
      for (const context of extraScans.contexts) await context.close();
    },
    { auto: true },
  ],
});

export { expect };

export async function signIn(page: Page, key: string) {
  await page.goto("/login");
  await page.getByLabel("Admin API key").fill(key);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await page.waitForLoadState("networkidle");
}

export async function screenshot(page: Page, name: string) {
  if (process.env.CONSOLE_SCREENSHOTS !== "1" && process.env.CONSOLE_CURATED_SCREENSHOTS !== "1")
    return;
  const images = resolve("../docs/images");
  mkdirSync(images, { recursive: true });
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.documentElement.classList.add("screenshot-capture");
    (document.activeElement as HTMLElement)?.blur();
  });
  await page.screenshot({ path: resolve(images, `console-${name}.png`), fullPage: true });
  await page.evaluate(() => document.documentElement.classList.remove("screenshot-capture"));
}
