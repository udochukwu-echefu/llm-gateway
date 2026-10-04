import { test, expect } from "./fixtures";
import { profileMenuDemoSecurityTests } from "./profile-menu-demo-security";
import { profileMenuReadRaceTests } from "./profile-menu-demo-read-race";
import {
  trigger,
  actions,
  open,
  explore,
  choose,
  assertReadOnly,
  assertNorthwind,
} from "./profile-menu-demo-controls";

export function profileMenuDemoTests() {
  test("phone touch opens and pins the profile card without hover", async ({ newScannedPage }) => {
    const page = await newScannedPage({ hasTouch: true, viewport: { width: 375, height: 844 } });
    await explore(page);
    await trigger(page).tap();
    await expect(actions(page)).toBeVisible();
    await actions(page).getByRole("button", { name: "Dark", exact: true }).tap();
    await expect(actions(page).getByRole("button", { name: "Dark", exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.touchscreen.tap(8, 8);
    await expect(actions(page)).not.toBeVisible();
  });
  test("profile switch blocks duplicate submissions while the real auth route is pending", async ({
    page,
  }) => {
    await explore(page);
    await open(page);
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let requests = 0;
    await page.route("**/api/auth/demo", async (route) => {
      requests++;
      await gate;
      await route.fallback();
    });
    const switched = page.waitForResponse(
      (r) => r.url().endsWith("/api/auth/demo") && r.request().method() === "POST",
    );
    const target = actions(page).getByRole("button", { name: /^Northwind Health viewer/ });
    await target.click();
    await expect(target).toBeDisabled();
    await expect(target).toContainText("Switching…");
    await target.evaluate((button) => (button as HTMLButtonElement).click());
    await expect(trigger(page)).toHaveAttribute("aria-label", "Profile menu: Platform viewer");
    await expect.poll(() => requests).toBe(1);
    release();
    expect((await switched).status()).toBe(200);
    await expect(trigger(page)).toHaveAttribute(
      "aria-label",
      "Profile menu: Northwind Health viewer",
    );
    await page.waitForLoadState("networkidle");
    await assertNorthwind(page);
  });
  test("profile menu replaces the real server session Platform → Northwind → Platform without stale scope", async ({
    page,
    context,
    responseBody,
    scannedResponses,
  }) => {
    await explore(page);
    const cookie = (await context.cookies()).find((c) => c.name === "__Host-lgw-console")!;
    expect({ secure: cookie.secure, httpOnly: cookie.httpOnly, sameSite: cookie.sameSite }).toEqual(
      { secure: true, httpOnly: true, sameSite: "Strict" },
    );
    await assertReadOnly(page);
    await open(page);
    await actions(page).getByRole("button", { name: "Dark", exact: true }).click();
    await page.keyboard.press("Escape");
    await scannedResponses.settle();
    await page.goto("/orgs/Demo%20Co");
    await expect(page.getByRole("heading", { name: "Demo Co", exact: true })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => {
      (window as Window & { previousScope?: boolean }).previousScope = true;
    });

    await scannedResponses.settle();
    await choose(page, "org", responseBody);

    expect(
      await page.evaluate(() => (window as Window & { previousScope?: boolean }).previousScope),
    ).toBeUndefined();
    const newCookie = (await context.cookies()).find((c) => c.name === "__Host-lgw-console")!;
    expect(newCookie.value).not.toBe(cookie.value);
    await assertNorthwind(page);
    await assertReadOnly(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await scannedResponses.settle();
    await page.reload();
    await assertNorthwind(page);
    await scannedResponses.settle();
    await page.goBack();
    await assertNorthwind(page);
    await expect(
      page.getByRole("alert").filter({ hasText: "Organization not found" }),
    ).toBeVisible();
    await expect(page.getByRole("cell", { name: "Search", exact: true })).toHaveCount(0);
    await scannedResponses.settle();
    await page.goto("/settings");
    await expect(page.locator(".settings-panel .identity-name")).toHaveText(
      "Demo visitor · Northwind Health viewer",
    );
    await scannedResponses.settle();
    await choose(page, "platform", responseBody);
    await expect(
      page
        .getByRole("navigation", { name: "Main navigation" })
        .getByRole("link", { name: "Providers", exact: true }),
    ).toBeVisible();
    const names = await page.evaluate(async () =>
      (await (await fetch("/api/admin/orgs")).json()).data.map((org: { name: string }) => org.name),
    );
    expect(names).toEqual(expect.arrayContaining(["Demo Co", "Northwind Health", "Orbit Labs"]));
    await assertReadOnly(page);
    await open(page);
    await expect(actions(page).getByRole("button", { name: /^Platform viewer/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await scannedResponses.settle();
    await actions(page).getByRole("button", { name: "Sign out", exact: true }).click();
    await expect(page).toHaveURL(/\/login$/);
    expect((await context.cookies()).some((c) => c.name === "__Host-lgw-console")).toBe(false);
    await scannedResponses.settle();
    await page.goBack();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("profile preview has no network activity; touch, pinned dismissal, focus and reduced motion work", async ({
    page,
  }) => {
    await explore(page);
    await page.waitForLoadState("networkidle");
    const requests: string[] = [];
    page.on("request", (r) => requests.push(r.url()));
    await trigger(page).hover();
    await expect(actions(page)).toBeVisible();
    const profileChoice = actions(page).getByRole("button", { name: /^Northwind Health viewer/ });
    await profileChoice.hover();
    expect(await profileChoice.evaluate((e) => getComputedStyle(e).backgroundColor)).toBe(
      "rgba(0, 0, 0, 0)",
    );
    await page.mouse.move(0, 0);
    await expect(actions(page)).not.toBeVisible();
    await trigger(page).click();
    await page.mouse.move(0, 0);
    await expect(actions(page)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(trigger(page)).toBeFocused();
    await trigger(page).click();
    await page.locator("h1").click();
    await expect(actions(page)).not.toBeVisible();
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: 375, height: 420 });
    await trigger(page).focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("Tab");
    await expect(actions(page).getByRole("link", { name: "View profile" })).toBeFocused();
    await actions(page).getByRole("button", { name: "System", exact: true }).focus();
    const bounds = await actions(page)
      .getByRole("button", { name: "System", exact: true })
      .boundingBox();
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(420);
    expect(
      await page.locator(".profile-reveal").evaluate((e) => getComputedStyle(e).transitionDuration),
    ).toBe("0s");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect(requests).toEqual([]);
  });

  test("current profile is a no-op and unavailable/429/network errors preserve identity and allow retry", async ({
    page,
    responseBody,
  }) => {
    await explore(page);
    await open(page);
    let submissions = 0;
    page.on("request", (r) => {
      if (r.url().endsWith("/api/auth/demo") && r.method() === "POST") submissions++;
    });
    await actions(page)
      .getByRole("button", { name: /^Platform viewer/ })
      .click();
    expect(submissions).toBe(0);
    for (const [status, error] of [
      [429, "Too many sign-in attempts. Please try again in a minute."],
      [503, "The demo is unavailable. Please try again later."],
    ] as const) {
      await page.route("**/api/auth/demo", (route) =>
        route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ error }) }),
      );
      await actions(page)
        .getByRole("button", { name: /^Northwind Health viewer/ })
        .click();
      await expect(actions(page).getByRole("alert")).toContainText(error);
      await expect(trigger(page)).toHaveAttribute("aria-label", "Profile menu: Platform viewer");
      await expect(
        actions(page).getByRole("button", { name: /^Northwind Health viewer/ }),
      ).toBeEnabled();
      await page.unroute("**/api/auth/demo");
    }
    await page.route("**/api/auth/demo", (route) => route.abort());
    await actions(page)
      .getByRole("button", { name: /^Northwind Health viewer/ })
      .click();
    await expect(actions(page).getByRole("alert")).toContainText("current session is unchanged");
    await expect(trigger(page)).toHaveAttribute("aria-label", "Profile menu: Platform viewer");
    await page.unroute("**/api/auth/demo");
    await choose(page, "org", responseBody);
    await assertNorthwind(page);
  });

  test("Appearance shares Settings/header state, survives profile reload and System follows the OS", async ({
    page,
    responseBody,
  }) => {
    await explore(page);
    await open(page);
    const mutations: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/api/admin") && r.method() !== "GET") mutations.push(r.url());
    });
    for (const theme of ["Light", "Dark", "System"]) {
      await actions(page).getByRole("button", { name: theme, exact: true }).click();
      await expect(actions(page).getByRole("button", { name: theme, exact: true })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme.toLowerCase());
    }
    await page.emulateMedia({ colorScheme: "dark" });
    await expect
      .poll(() => page.locator("html").evaluate((e) => getComputedStyle(e).colorScheme))
      .toBe("dark");
    await page.emulateMedia({ colorScheme: "light" });
    await expect
      .poll(() => page.locator("html").evaluate((e) => getComputedStyle(e).colorScheme))
      .toBe("light");
    await choose(page, "org", responseBody);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "system");
    await page.goto("/settings");
    await expect(page.getByRole("combobox", { name: "Theme", exact: true })).toHaveAttribute(
      "data-value",
      "system",
    );
    await page.getByRole("button", { name: "Switch to dark theme" }).click();
    await open(page);
    await expect(actions(page).getByRole("button", { name: "Dark", exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(mutations).toEqual([]);
  });
  profileMenuDemoSecurityTests();
  profileMenuReadRaceTests();
}
