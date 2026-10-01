import { test, expect, screenshot } from "./fixtures";
import type { Page } from "@playwright/test";

async function explore(page: Page, scope: "platform" | "org") {
  await page.goto("/login");
  await page
    .getByRole("button", {
      name:
        scope === "platform"
          ? "Explore as platform operator (read-only)"
          : "Explore as Northwind Health org admin (read-only)",
    })
    .click();
  await expect(page).toHaveURL(/\/overview$/);
  await expect(
    page.getByText(scope === "platform" ? "Platform viewer" : "Organisation viewer", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Read-only demo. Changes are disabled; this is a live gateway with synthetic data.",
    ),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Organisations", exact: true })).toBeVisible();
}
for (const scope of ["platform", "org"] as const) {
  test(`Explore button signs in as ${scope} viewer`, async ({ page }) => {
    if (scope === "platform") {
      await page.goto("/login");
      await screenshot(page, "public-demo-login");
    }
    await explore(page, scope);
    await screenshot(page, `public-demo-${scope}`);
  });
  test(`public demo tour visits every screen as ${scope} viewer`, async ({ page }) => {
    test.setTimeout(240000);
    await explore(page, scope);
    const org = scope === "platform" ? "Demo Co" : "Northwind Health";
    const team = scope === "platform" ? "Search" : "Clinical";
    for (const screen of [
      "overview",
      "orgs",
      "requests",
      "analytics",
      "keys",
      "models",
      "audit",
      "settings",
      ...(scope === "platform" ? ["providers"] : []),
    ]) {
      await page.goto(`/${screen}?org=${encodeURIComponent(org)}`);
      await page.waitForLoadState("networkidle");
      await expect(page.locator("main .skeleton")).toHaveCount(0);
      await expect(page.locator("main h1")).toBeVisible();
      await expect(page.locator("main [role=alert]")).toHaveCount(0);
    }
    for (const [path, tabs] of [
      [`/orgs/${encodeURIComponent(org)}`, ["Overview", "Policies", "Cache"]],
      [
        `/orgs/${encodeURIComponent(org)}/teams/${team}`,
        ["API keys", "Limits", "Budget", "Policies", "Cache"],
      ],
    ] as const) {
      await page.goto(path);
      for (const tab of tabs) {
        await page.getByRole("button", { name: tab, exact: true }).click();
        await page.waitForLoadState("networkidle");
        await expect(page.locator("main .skeleton")).toHaveCount(0);
        await expect(page.locator("main [role=alert]")).toHaveCount(0);
        const mutations = page.getByRole("button", {
          name: /^(Create |Save |Remove override|Clear overrides|Purge cache|Revoke )/,
        });
        if (tab !== "Overview") await expect(mutations.first()).toBeVisible();
        for (const button of await mutations.all()) await expect(button).toBeDisabled();
        if (scope === "platform" && tab === "Limits")
          await screenshot(page, "public-demo-read-only-controls");
      }
    }
    await page.goto(`/requests?org=${encodeURIComponent(org)}`);
    const exported = await page.evaluate(
      async () =>
        (await fetch(`/api/export/requests?${new URLSearchParams(location.search)}`)).status,
    );
    expect(exported).toBe(200);
    await page.keyboard.press("Meta+k");
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    if (scope === "org") {
      const status = await page.evaluate(
        async () => (await fetch("/api/admin/orgs/Demo%20Co/teams")).status,
      );
      expect(status).toBe(404);
    }
  });
}
test("public viewer direct BFF mutation attempts return 403", async ({ page }) => {
  await explore(page, "platform");
  const results = await page.evaluate(async () =>
    Promise.all(
      [
        ["POST", "/orgs"],
        ["PUT", "/orgs/Demo%20Co/model-policy"],
        ["DELETE", "/orgs/Demo%20Co/model-policy"],
        ["POST", "/orgs/Demo%20Co/cache/purge"],
      ].map(async ([method, path]) => {
        const response = await fetch(`/api/admin${path}`, {
          method,
          body: "bad",
          headers: { "Content-Type": "application/json" },
        });
        return { status: response.status, code: (await response.json()).code };
      }),
    ),
  );
  expect(results).toEqual(Array(4).fill({ status: 403, code: "read_only_admin" }));
});
test("public demo hides paste-key form and disables key login route", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByLabel("Admin API key")).toHaveCount(0);
  const status = await page.evaluate(
    async () => (await fetch("/api/auth/login", { method: "POST", body: "{}" })).status,
  );
  expect(status).toBe(404);
  const adminResponse = await page.evaluate(async () => {
    const response = await fetch("/admin/v1/me");
    await response.text();
    return { path: new URL(response.url).pathname, type: response.headers.get("Content-Type") };
  });
  expect(adminResponse.path).toBe("/login");
  expect(adminResponse.type).toContain("text/html");
});
