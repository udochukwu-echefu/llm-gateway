import { test, expect, signIn } from "./fixtures";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import type { Page } from "@playwright/test";
async function capture(page: Page, role: string, profile: string, name: string, fullPage = true) {
  await expect(page.locator("main .skeleton")).toHaveCount(0);
  if (process.env.CONSOLE_SCREENSHOTS !== "1") return;
  const directory = resolve(`../docs/images/console/${role}/${profile}`);
  mkdirSync(directory, { recursive: true });
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    (document.activeElement as HTMLElement)?.blur();
    document.documentElement.classList.add("screenshot-capture");
  });
  await page.screenshot({ path: resolve(directory, `${name}.png`), fullPage });
  await page.evaluate(() => document.documentElement.classList.remove("screenshot-capture"));
}
for (const role of ["platform", "org"] as const) {
  test(`demo tour every screen and tab as ${role} admin`, async ({ page, credentials }) => {
    test.setTimeout(360000);
    await signIn(page, role === "platform" ? credentials.demoPlatform : credentials.demoOrg);
    const org = role === "platform" ? "Demo Co" : "Northwind Health";
    const team = role === "platform" ? "Search" : "Clinical";
    const profiles =
      process.env.CONSOLE_SCREENSHOTS === "1"
        ? [
            { name: "light", width: 1440, height: 1050, theme: "light" },
            { name: "dark", width: 1440, height: 1050, theme: "dark" },
            { name: "tablet", width: 820, height: 1050, theme: "light" },
            { name: "phone", width: 390, height: 844, theme: "light" },
          ]
        : [{ name: "light", width: 1440, height: 1050, theme: "light" }];
    for (const profile of profiles) {
      await page.setViewportSize({ width: profile.width, height: profile.height });
      await page.getByLabel("Theme", { exact: true }).first().selectOption(profile.theme);
      const pages = [
        "overview",
        ...(role === "platform" ? ["orgs", "providers"] : []),
        "requests",
        "analytics",
        "keys",
        "models",
        "audit",
        "settings",
      ];
      for (const screen of pages) {
        await page.goto(
          `/${screen}?org=${encodeURIComponent(org)}${screen === "analytics" ? "&group_by=provider" : ""}`,
        );
        await page.waitForLoadState("networkidle");
        await expect(page.locator("main h1")).toBeVisible();
        await expect(page.locator("main [role=alert]")).toHaveCount(0);
        if (["requests", "analytics", "keys", "audit"].includes(screen))
          await expect(page.locator("main tbody tr").first()).toBeVisible();
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
        ).toBe(true);
        if (screen === "requests") await page.getByText("Request filters", { exact: true }).click();
        if (screen === "overview" && role === "platform") {
          const over = page.getByRole("progressbar", { name: "Search budget used", exact: true });
          await expect(over).toHaveClass("danger");
          const warning = page.getByRole("progressbar", {
            name: "Support budget used",
            exact: true,
          });
          await expect(warning).toHaveClass("warning");
          expect(
            await over.evaluate((bar) =>
              getComputedStyle(bar).getPropertyValue("--progress-fill").trim(),
            ),
          ).not.toBe(
            await warning.evaluate((bar) =>
              getComputedStyle(bar).getPropertyValue("--progress-fill").trim(),
            ),
          );
        }
        await capture(page, role, profile.name, screen);
      }
      await page.goto(`/requests?org=${encodeURIComponent(org)}&fallback=true&retried=true`);
      await page
        .getByRole("button", { name: /^demo-/ })
        .first()
        .click();
      await expect(page.getByRole("heading", { name: "Attempt 3: deepseek 200" })).toBeVisible();
      await capture(page, role, profile.name, "request-detail", false);
      await page.getByRole("button", { name: "Close", exact: true }).click();
      await page.goto("/audit");
      await page
        .getByRole("button", { name: /^Event \d/ })
        .first()
        .click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await capture(page, role, profile.name, "audit-detail", false);
      await page.getByRole("button", { name: "Close", exact: true }).click();
      for (const [level, path, tabs] of [
        ["org", `/orgs/${encodeURIComponent(org)}`, ["Overview", "Policies", "Cache"]],
        [
          "team",
          `/orgs/${encodeURIComponent(org)}/teams/${encodeURIComponent(team)}`,
          ["API keys", "Limits", "Budget", "Policies", "Cache"],
        ],
      ] as const) {
        await page.goto(path);
        for (const tab of tabs) {
          await page.getByRole("button", { name: tab, exact: true }).click();
          await page.waitForLoadState("networkidle");
          await expect(page.locator("main [role=alert]")).toHaveCount(0);
          if (tab === "API keys") await expect(page.locator("main tbody tr").first()).toBeVisible();
          await capture(
            page,
            role,
            profile.name,
            `${level}-${tab.toLowerCase().replaceAll(" ", "-")}`,
          );
        }
      }
      if (role === "platform") {
        await page.goto("/orgs/Orbit%20Labs");
        await expect(page.getByRole("link", { name: "Prototypes", exact: true })).toBeVisible();
        await capture(page, role, profile.name, "orbit-near-empty");
        await page.goto("/orgs/Demo%20Co/teams/Paused%20sandbox");
        await page.getByRole("button", { name: "Policies", exact: true }).click();
        await expect(
          page
            .getByRole("region", { name: "Model policy", exact: true })
            .getByText("No usable models.", { exact: true }),
        ).toBeVisible();
        await capture(page, role, profile.name, "paused-sandbox");
      }
    }
  });
}
