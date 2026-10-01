import { test, expect, signIn, screenshot } from "./fixtures";
import { abusiveLogin } from "./attacks";

test("platform workflow", async ({ page, context, credentials, recordKey }) => {
  await signIn(page, credentials.platform);
  await page.goto("/orgs");
  await expect(page.getByRole("link", { name: credentials.org, exact: true })).toBeVisible();
  await screenshot(page, "organisations");
  const org = "E2E workspace";
  const team = "Applications";
  await page.getByLabel("Organisation name").fill(org);
  await page.getByRole("button", { name: "Create organisation" }).click();
  await page.getByRole("link", { name: org, exact: true }).click();
  await page.getByLabel("Team name").fill(team);
  await page.getByRole("button", { name: "Create team", exact: true }).click();
  await page.getByRole("link", { name: team, exact: true }).click();
  await expect(page.getByRole("button", { name: "Create API key" })).toBeVisible();
  // Prepare a revocation fixture privately. Browser key creation is its own test below.
  const prepared = await context.request.post(
    `http://127.0.0.1:18091/admin/v1/orgs/${encodeURIComponent(org)}/teams/${team}/keys`,
    {
      headers: { Authorization: `Bearer ${credentials.platform}` },
      data: { name: "Fake revocation fixture" },
    },
  );
  expect(prepared.status()).toBe(200);
  const key = await prepared.json();
  recordKey(key.key);
  await page.reload();
  await page.getByRole("button", { name: "Limits", exact: true }).click();
  await page.getByLabel("Requests per minute").fill("120");
  await page.getByLabel("Tokens per minute").fill("50000");
  await page.getByLabel("Max concurrency").fill("8");
  await page.getByRole("button", { name: "Save limits" }).click();
  await expect(page.getByText("Limits saved.", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Override", exact: true })).toHaveCount(3);
  await screenshot(page, "limits");
  await page.getByRole("button", { name: "Clear overrides" }).click();
  await expect(page.getByText("Overrides cleared.", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Override", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Budget", exact: true }).click();
  await page.getByLabel("Monthly budget (USD)").fill("25.000000000001");
  await page.getByLabel("Alert threshold (0–1)").fill("0.75");
  await page.getByRole("button", { name: "Save budget" }).click();
  await expect(page.getByText("Budget saved.", { exact: true })).toBeVisible();
  await expect(page.getByText("$25.000000000001", { exact: false })).toBeVisible();
  await screenshot(page, "budget");
  await page.getByRole("button", { name: "API keys", exact: true }).click();
  await page.getByRole("button", { name: `Revoke ${key.key_id}`, exact: true }).click();
  await expect(page.getByRole("button", { name: "Confirm revoke" })).toBeDisabled();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Confirm revoke" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText("Revoked", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Audit log", exact: true }).click();
  await page.getByRole("button", { name: "Verify chain" }).click();
  await expect(page.getByText(/^Chain verified:/)).toBeVisible();
  await page
    .getByLabel("Actor", { exact: true })
    .fill(`admin:${credentials.platform.split("_")[1]}`);
  for (const action of [
    "create-org",
    "create-team",
    "create-key",
    "set-limits",
    "clear-limits",
    "set-budget",
    "revoke-key",
  ]) {
    await page.getByRole("combobox", { name: "Action", exact: true }).selectOption(action);
    await page.getByRole("button", { name: "Apply filters" }).click();
    await expect(page).toHaveURL(new RegExp(`action=${action}`));
    await expect(page.getByRole("cell", { name: action, exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText(key.key_id, { exact: true })).toBeVisible();
  await screenshot(page, "audit");
});

test("one-time key dialog", async ({ page, credentials, recordKey }) => {
  await signIn(page, credentials.platform);
  await page.goto(`/orgs/${encodeURIComponent(credentials.org)}/teams/Search`);
  await page.getByLabel("Key name").fill("Fake application key");
  await page.getByLabel("Expires in days").fill("30");
  await page.getByRole("button", { name: "Create API key" }).click();
  const secret = (await page.getByTestId("created-key").textContent())!;
  expect(Boolean(secret?.startsWith("lgw_"))).toBe(true);
  recordKey(secret, true);
  await expect(page.getByRole("dialog")).toContainText("You won’t see this again");
  for (const key of ["Shift+Tab", "Tab"]) {
    await page.keyboard.press(key);
    expect(await page.evaluate(() => Boolean(document.activeElement?.closest("dialog")))).toBe(
      true,
    );
  }
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect((await page.content()).includes(secret)).toBe(false);
  await page.reload();
  await expect(page.getByRole("button", { name: "Create API key" })).toBeVisible();
  expect((await page.content()).includes(secret)).toBe(false);
  await expect(page.getByRole("button", { name: /reveal|show key|reopen/i })).toHaveCount(0);
  await screenshot(page, "keys");
});

test("org-admin isolation and URL tampering", async ({ page, credentials }) => {
  await signIn(page, credentials.orgKey);
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole("link", { name: credentials.other, exact: true })).toHaveCount(0);
  for (const path of ["", "/teams/Private%20team"]) {
    await page.goto(`/orgs/${encodeURIComponent(credentials.other)}${path}`);
    await expect(page.getByText("Organization not found", { exact: true })).toBeVisible();
  }
  await page.goto("/audit");
  await expect(page.getByRole("button", { name: "Verify chain" })).toHaveCount(0);
  const statuses = await page.evaluate(async () => {
    const forbidden = await fetch("/api/admin/audit/verify");
    await forbidden.arrayBuffer();
    const escaped = await fetch("/api/admin/orgs/Other%2520workspace/teams");
    await escaped.arrayBuffer();
    return [forbidden.status, escaped.status];
  });
  expect(statuses).toEqual([403, 404]);
});

test("security headers and CSP", async ({ page, credentials }) => {
  const cspErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && /Content Security Policy/.test(message.text())) {
      cspErrors.push(message.text());
    }
  });
  const login = await page.goto("/login");
  const headers = login!.headers();
  const csp = headers["content-security-policy"];
  expect(csp).toMatch(/script-src[^;]*'nonce-[^']+'/);
  expect(csp).not.toContain("unsafe-inline");
  expect(csp).not.toContain("unsafe-eval");
  expect(csp).toContain("frame-ancestors 'none'");
  expect(headers["referrer-policy"]).toBe("no-referrer");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  await screenshot(page, "login");
  await signIn(page, credentials.platform);
  await page.goto(`/orgs/${encodeURIComponent(credentials.org)}`);
  await expect(page.getByRole("img", { name: "Daily total tokens" })).toBeVisible();
  await expect(page.getByText("Unpriced usage", { exact: false }).first()).toBeVisible();
  await screenshot(page, "usage");
  for (const theme of ["light", "dark"]) {
    await page.getByLabel("Theme", { exact: true }).selectOption(theme);
    const fillsHeight = await page.evaluate(() => {
      const aside = document.querySelector("aside")!.getBoundingClientRect().height;
      const frame = document.querySelector(".console")!.getBoundingClientRect().height;
      return Math.abs(aside - frame) <= 1;
    });
    expect(fillsHeight, "Sidebar background fills the entire console height").toBe(true);
  }
  await screenshot(page, "usage-dark");
  await page.setViewportSize({ width: 820, height: 1100 });
  await screenshot(page, "tablet");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  expect(cspErrors.length, "Production browser must have no CSP violations").toBe(0);
});

test("cookie flags and cross-origin POST", async ({ page, context, credentials }) => {
  await signIn(page, credentials.platform);
  const cookie = (await context.cookies()).find((item) => item.name === "__Host-lgw-console")!;
  expect(cookie.httpOnly).toBe(true);
  expect(cookie.secure).toBe(true);
  expect(cookie.sameSite).toBe("Strict");
  expect((await page.evaluate(() => document.cookie)).includes("lgw-console")).toBe(false);
  for (const origin of ["https://evil.invalid", undefined]) {
    for (const path of ["/api/auth/login", "/api/auth/logout", "/api/admin/orgs"]) {
      const response = await context.request.post(path, {
        headers: origin ? { Origin: origin } : {},
        data: { name: "fake-cross-origin", key: "fake" },
      });
      expect(response.status()).toBe(403);
    }
  }
});

test("revocation logs out", async ({ page, context, credentials }) => {
  await signIn(page, credentials.revocable);
  await page.waitForLoadState("networkidle");
  const response = await context.request.post(
    `http://127.0.0.1:18091/admin/v1/keys/${credentials.revocable.split("_")[1]}/revoke`,
    { headers: { Authorization: `Bearer ${credentials.platform}` } },
  );
  expect(response.status()).toBe(200);
  await page.goto("/orgs");
  await expect(page).toHaveURL(/\/login$/);
  expect((await context.cookies()).some((item) => item.name === "__Host-lgw-console")).toBe(false);
});

test("login throttle and no shared-IP lockout", async ({ page, context, credentials }) => {
  await signIn(page, credentials.platform);
  const invalid = "lgwa_aaaaaaaaaaaa_" + "A".repeat(43);
  let status = 0;
  for (let index = 0; index < 21; index++) {
    const response = await context.request.get("http://127.0.0.1:18091/admin/v1/me", {
      headers: { Authorization: `Bearer ${invalid}` },
    });
    status = response.status();
  }
  expect(status).toBe(429);
  let abusive;
  for (let index = 0; index < 26; index++) abusive = await abusiveLogin(index);
  expect(abusive!.status).toBe(429);
  expect(abusive!.error).toBe("Too many sign-in attempts. Please try again in a minute.");
  // Valid gateway credentials still work from the BFF's exhausted shared IP.
  await page.goto("/audit");
  await expect(page.getByRole("button", { name: "Verify chain" })).toBeVisible();
  await page.getByRole("button", { name: "Verify chain" }).click();
  await expect(page.getByText(/^Chain verified:/)).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await signIn(page, credentials.platform);
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
});
