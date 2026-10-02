import { expect } from "./fixtures";
import type { Page, Request } from "@playwright/test";

export const trigger = (page: Page) => page.getByRole("button", { name: /^Profile menu:/ });
export const actions = (page: Page) => page.getByRole("region", { name: "Profile actions" });
export async function open(page: Page) {
  if ((await trigger(page).getAttribute("aria-expanded")) !== "true") await trigger(page).click();
}
export async function explore(page: Page) {
  await page.goto("/login");
  const button = page.getByRole("button", {
    name: "Explore as platform operator (read-only)",
    exact: true,
  });
  await submit(page, () => button.click());
  await expect(page).toHaveURL(/\/overview$/);
  await page.waitForLoadState("networkidle");
}
export async function choose(
  page: Page,
  scope: "platform" | "org",
  responseBody: (request: Request) => string,
) {
  await open(page);
  const document = page.waitForRequest(
    (r) =>
      r.isNavigationRequest() &&
      r.resourceType() === "document" &&
      new URL(r.url()).pathname === "/overview",
  );
  const result = await submit(page, () =>
    actions(page)
      .getByRole("button", {
        name: scope === "platform" ? /^Platform viewer/ : /^Northwind Health viewer/,
      })
      .click(),
  );
  expect(result.headers()["cache-control"]).toBe("no-store");
  const { identity } = JSON.parse(responseBody(result.request()));
  expect(identity.role).toBe("viewer");
  expect(identity.organization?.name ?? null).toBe(scope === "org" ? "Northwind Health" : null);
  await document;
  await expect(trigger(page)).toHaveAttribute(
    "aria-label",
    `Profile menu: ${scope === "platform" ? "Platform viewer" : "Northwind Health viewer"}`,
  );
  await page.waitForLoadState("networkidle");
}
export async function assertReadOnly(page: Page) {
  expect(
    await page.evaluate(async () => {
      const response = await fetch("/api/admin/orgs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "Never created" }),
      });
      return { status: response.status, code: (await response.json()).code };
    }),
  ).toEqual({ status: 403, code: "read_only_admin" });
}
export async function assertNorthwind(page: Page) {
  await expect(trigger(page)).toHaveAttribute(
    "aria-label",
    "Profile menu: Northwind Health viewer",
  );
  await expect(
    page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("link", { name: "Providers", exact: true }),
  ).toHaveCount(0);
  const data = await page.evaluate(async () => {
    const response = await fetch("/api/admin/orgs");
    const foreign = await fetch("/api/admin/orgs/Demo%20Co/teams");
    return {
      names: (await response.json()).data.map((org: { name: string }) => org.name),
      foreign: foreign.status,
    };
  });
  expect(data).toEqual({ names: ["Northwind Health"], foreign: 404 });
}

async function submit(page: Page, click: () => Promise<void>) {
  const send = async () => {
    const response = page.waitForResponse(
      (r) => r.url().endsWith("/api/auth/demo") && r.request().method() === "POST",
    );
    await click();
    return response;
  };
  let response = await send();
  if (response.status() === 429) {
    expect((await response.json()).error).toBe(
      "Too many sign-in attempts. Please try again in a minute.",
    );
    const seconds = Number(response.headers()["retry-after"]);
    expect(seconds).toBeGreaterThan(0);
    expect(seconds).toBeLessThanOrEqual(60);
    console.log(
      `Real demo sign-in quota retained; waiting Retry-After ${seconds}s for test isolation.`,
    );
    await page.waitForTimeout((seconds + 1) * 1000);
    response = await send();
  }
  expect(response.status()).toBe(200);
  return response;
}
