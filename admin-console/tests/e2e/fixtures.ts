import {
  test as base,
  expect,
  type Page,
  type BrowserContext,
  type Locator,
  type Request,
} from "@playwright/test";
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
  scannedResponses: Awaited<ReturnType<typeof responseScanner>>;
  responseBody: (request: Request) => string;
  credentials: Credentials;
  coverage: void;
  extraScans: {
    scanners: Awaited<ReturnType<typeof responseScanner>>[];
    contexts: BrowserContext[];
  };
  newScannedPage: (options?: {
    hasTouch?: boolean;
    viewport?: { width: number; height: number };
  }) => Promise<Page>;
  recordKey: (key: string, permitCreation?: boolean) => void;
}

export const test = base.extend<Fixtures, { leaks: LeakTotals }>({
  scannedResponses: async ({ page }, provide) => {
    await provide(await responseScanner(page));
  },
  responseBody: async ({ scannedResponses }, provide) => {
    await provide((request) => {
      const body = scannedResponses.bodyFor(request);
      expect(body, "Response bytes captured before navigation").toBeDefined();
      return body!;
    });
  },
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
    await provide(async (options = {}) => {
      const context = await browser.newContext({
        baseURL: `http://${process.env.DEMO_APPLIANCE_E2E === "1" ? "localhost" : "[::1]"}:${process.env.CONSOLE_TEST_PORT ?? "3100"}`,
        viewport: { width: 1440, height: 1050 },
        ...options,
      });
      const page = await context.newPage();
      extraScans.contexts.push(context);
      extraScans.scanners.push(await responseScanner(page));
      return page;
    });
  },
  coverage: [
    async ({ scannedResponses: scanner, credentials, leaks, extraScans }, provide, info) => {
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
  await page.getByRole("button", { name: /^Profile menu:/ }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.mouse.move(0, 0);
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

export async function selectChoice(control: Locator, value: string) {
  await control.click();
  // The custom menu retains the visible label and the original option value.
  const label = await control.getAttribute("aria-label");
  await control
    .page()
    .getByRole("listbox", { name: label!, exact: true })
    .locator(`[role="option"][data-value="${value}"]`)
    .click();
  await expect(control).toHaveAttribute("data-value", value);
}

export async function setTheme(page: Page, theme: string) {
  const toggle = page.getByRole("button", { name: `Switch to ${theme} theme`, exact: true });
  if (await toggle.isVisible()) await toggle.click();
  await expect
    .poll(() => page.locator("html").evaluate((element) => getComputedStyle(element).colorScheme))
    .toBe(theme);
}
