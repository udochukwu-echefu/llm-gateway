import { test, expect, signIn, screenshot } from "./fixtures";
import type { Page, APIRequestContext } from "@playwright/test";
async function reset(request: APIRequestContext, org: string, key: string) {
  for (const kind of ["model-policy", "guardrails", "residency"])
    for (const query of ["", "?team=Search"]) {
      const response = await request.delete(
        `http://127.0.0.1:18091/admin/v1/orgs/${encodeURIComponent(org)}/${kind}${query}`,
        { headers: { Authorization: `Bearer ${key}` } },
      );
      expect(response.status()).toBe(200);
    }
}
async function policies(page: Page, org: string, team = false) {
  await page.goto(`/orgs/${encodeURIComponent(org)}${team ? "/teams/Search" : ""}`);
  await page.getByRole("button", { name: "Policies", exact: true }).click();
  await expect(page.getByRole("region", { name: "Model policy", exact: true })).toBeVisible();
}
async function save(page: Page, title: string) {
  const panel = page.getByRole("region", { name: title, exact: true });
  await panel.getByRole("button", { name: `Save ${title.toLowerCase()}`, exact: true }).click();
  await expect(panel.getByRole("status").filter({ hasText: "Policy saved" })).toBeVisible();
}
test("org policy and team intersection enforced by public API", async ({
  page,
  context,
  credentials,
  recordKey,
}) => {
  await reset(context.request, credentials.org, credentials.platform);
  await signIn(page, credentials.orgKey);
  await policies(page, credentials.org);
  let panel = page.getByRole("region", { name: "Model policy", exact: true });
  await panel.getByLabel("Allow only these", { exact: true }).check();
  await panel.getByLabel("Whole provider · groq/*").check();
  await save(page, "Model policy");
  await policies(page, credentials.org, true);
  panel = page.getByRole("region", { name: "Model policy", exact: true });
  await panel.getByLabel("Allow only these", { exact: true }).check();
  await panel.getByRole("checkbox", { name: /groq\/openai\/gpt-oss-20b/ }).check();
  await save(page, "Model policy");
  await expect(panel.getByText("Effective models · 1", { exact: true })).toBeVisible();
  await expect(panel.locator(".effective-models")).toContainText("groq/openai/gpt-oss-20b");
  await expect(panel.locator(".effective-models")).not.toContainText("groq/openai/gpt-oss-120b");
  const issued = await context.request.post(
    `http://127.0.0.1:18091/admin/v1/orgs/${encodeURIComponent(credentials.org)}/teams/Search/keys`,
    {
      headers: { Authorization: `Bearer ${credentials.platform}` },
      data: { name: "Fake policy verification key" },
    },
  );
  const key = (await issued.json()).key;
  recordKey(key);
  const denied = await context.request.post("http://127.0.0.1:18090/v1/chat/completions", {
    headers: { Authorization: `Bearer ${key}` },
    data: {
      model: "groq/openai/gpt-oss-120b",
      messages: [{ role: "user", content: "Synthetic denied request" }],
    },
  });
  expect(denied.status()).toBe(403);
  expect((await denied.json()).error.code).toBe("model_not_allowed");
  await screenshot(page, "policies-team");
});
test("guardrail tightening and weaker choice has no effect", async ({
  page,
  context,
  credentials,
}) => {
  await reset(context.request, credentials.org, credentials.platform);
  await signIn(page, credentials.orgKey);
  await policies(page, credentials.org);
  let panel = page.getByRole("region", { name: "Guardrails", exact: true });
  await panel.getByLabel("email action").selectOption("block");
  await save(page, "Guardrails");
  await expect(
    panel
      .getByRole("row")
      .filter({ has: page.getByLabel("email action") })
      .getByRole("cell")
      .last(),
  ).toHaveText("block");
  await policies(page, credentials.org, true);
  panel = page.getByRole("region", { name: "Guardrails", exact: true });
  await panel.getByLabel("email action").selectOption("allow");
  await expect(panel.getByText("No effect: the organisation already requires block")).toBeVisible();
  await save(page, "Guardrails");
  await expect(
    panel
      .getByRole("row")
      .filter({ has: page.getByLabel("email action") })
      .getByRole("cell")
      .last(),
  ).toHaveText("block");
});
test("EU residency shrinks usable models using the API view", async ({
  page,
  context,
  credentials,
}) => {
  await reset(context.request, credentials.org, credentials.platform);
  await signIn(page, credentials.orgKey);
  await policies(page, credentials.org);
  const panel = page.getByRole("region", { name: "Residency", exact: true });
  await expect(panel.getByText("Effective models · 7", { exact: true })).toBeVisible();
  await panel.getByLabel("Allow only these regions").check();
  await panel.getByRole("checkbox", { name: "eu European Union" }).check();
  await save(page, "Residency");
  await expect(panel.getByText("Effective models · 0", { exact: true })).toBeVisible();
  await expect(panel.getByText("No usable models.", { exact: true })).toBeVisible();
  await screenshot(page, "policies-org");
  await page.getByLabel("Theme", { exact: true }).selectOption("dark");
  await screenshot(page, "policies-dark");
  await page.setViewportSize({ width: 820, height: 1100 });
  await screenshot(page, "policies-tablet");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});
test("two browser contexts preserve the first policy and keep the conflicted draft", async ({
  page,
  context,
  credentials,
  newScannedPage,
}) => {
  await reset(context.request, credentials.org, credentials.platform);
  const other = await newScannedPage();
  await signIn(page, credentials.orgKey);
  await signIn(other, credentials.orgKey);
  await policies(page, credentials.org);
  await policies(other, credentials.org);
  const first = page.getByRole("region", { name: "Model policy", exact: true });
  const second = other.getByRole("region", { name: "Model policy", exact: true });
  await first.getByLabel("Allow only these", { exact: true }).check();
  await first.getByLabel("Whole provider · groq/*").check();
  await save(page, "Model policy");
  await second.getByLabel("Allow only these", { exact: true }).check();
  await second.getByLabel("Whole provider · deepseek/*").check();
  const response = other.waitForResponse(
    (r) => r.request().method() === "PUT" && r.url().includes("model-policy"),
  );
  await second.getByText("Save model policy", { exact: true }).click();
  expect((await response).status()).toBe(412);
  await expect(
    second.getByText("Someone else changed this policy. Reload to see their version"),
  ).toBeVisible();
  await expect(second.getByLabel("Whole provider · deepseek/*")).toBeChecked();
  const saved = await context.request.get(
    `http://127.0.0.1:18091/admin/v1/orgs/${encodeURIComponent(credentials.org)}/model-policy`,
    { headers: { Authorization: `Bearer ${credentials.orgKey}` } },
  );
  expect((await saved.json()).overrides.organization).toEqual(["groq/*"]);
});
test("cache purge requires a typed name and reports its count", async ({ page, credentials }) => {
  await signIn(page, credentials.orgKey);
  for (const team of [false, true]) {
    await page.goto(`/orgs/${encodeURIComponent(credentials.org)}${team ? "/teams/Search" : ""}`);
    await page.getByRole("button", { name: "Cache", exact: true }).click();
    await page.getByText("Purge cache", { exact: true }).click();
    await expect(page.getByText("Confirm purge", { exact: true })).toBeDisabled();
    await page.getByRole("textbox").fill(team ? "Search" : credentials.org);
    await page.getByText("Confirm purge", { exact: true }).click();
    await expect(page.getByText(/^Purged \d+ cached responses\.$/)).toBeVisible();
  }
  await screenshot(page, "cache-purge");
});
test("org admin cannot view or edit another org policies by URL tampering", async ({
  page,
  credentials,
}) => {
  await signIn(page, credentials.orgKey);
  await page.goto(`/orgs/${encodeURIComponent(credentials.other)}`);
  await expect(page.getByText("Organization not found", { exact: true })).toBeVisible();
  const statuses = await page.evaluate(
    async ({ other }) => {
      const results = [];
      for (const kind of ["model-policy", "guardrails", "residency"])
        for (const team of ["", "?team=Private%20team"]) {
          const path = `/api/admin/orgs/${encodeURIComponent(other)}/${kind}${team}`;
          for (const method of ["GET", "DELETE"]) {
            const response = await fetch(path, {
              method,
              headers: { "If-Match": '"' + "a".repeat(64) + '"' },
            });
            await response.arrayBuffer();
            results.push(response.status);
          }
        }
      return results;
    },
    { other: credentials.other },
  );
  expect(statuses).toEqual(Array(12).fill(404));
});
test("every policy write and cache purge appears in the audit log", async ({
  page,
  context,
  credentials,
}) => {
  await reset(context.request, credentials.org, credentials.platform);
  await signIn(page, credentials.orgKey);
  await policies(page, credentials.org);
  const models = page.getByRole("region", { name: "Model policy", exact: true });
  await models.getByLabel("Allow nothing").check();
  await models.getByText("Save model policy", { exact: true }).click();
  await page.getByText("Confirm change", { exact: true }).click();
  await expect(models.getByRole("status")).toContainText("Policy saved");
  await models.getByText("Remove override", { exact: true }).click();
  await page.getByText("Confirm change", { exact: true }).click();
  await expect(models.getByRole("status")).toContainText("Policy saved");
  const guards = page.getByRole("region", { name: "Guardrails", exact: true });
  await guards.getByLabel("phone action").selectOption("redact");
  await save(page, "Guardrails");
  await guards.getByText("Remove override", { exact: true }).click();
  await page.getByText("Confirm change", { exact: true }).click();
  await expect(guards.getByRole("status").filter({ hasText: "Policy saved" })).toBeVisible();
  const regions = page.getByRole("region", { name: "Residency", exact: true });
  await regions.getByLabel("Allow no regions").check();
  await regions.getByText("Save residency", { exact: true }).click();
  await page.getByText("Confirm change", { exact: true }).click();
  await expect(regions.getByRole("status")).toContainText("Policy saved");
  await regions.getByText("Remove override", { exact: true }).click();
  await page.getByText("Confirm change", { exact: true }).click();
  await expect(regions.getByRole("status")).toContainText("Policy saved");
  await page.getByRole("button", { name: "Cache", exact: true }).click();
  await page.getByText("Purge cache", { exact: true }).click();
  await page.getByRole("textbox").fill(credentials.org);
  await page.getByText("Confirm purge", { exact: true }).click();
  await expect(page.getByText(/^Purged/)).toBeVisible();
  await page.goto("/audit");
  for (const action of [
    "set-models",
    "clear-models",
    "set-guardrails",
    "clear-guardrails",
    "set-residency",
    "clear-residency",
    "cache-purge",
  ]) {
    await page.getByLabel("Action", { exact: true }).fill(action);
    await page.getByText("Filter events", { exact: true }).click();
    await expect(page.getByRole("cell", { name: action, exact: true }).first()).toBeVisible();
  }
});
test("unsaved policy changes warn before tab page and browser Back navigation", async ({
  page,
  credentials,
}) => {
  await signIn(page, credentials.orgKey);
  await policies(page, credentials.org);
  const panel = page.getByRole("region", { name: "Model policy", exact: true });
  await panel.getByLabel("Allow nothing").check();
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Cache", exact: true }).click();
  await expect(panel.getByLabel("Allow nothing")).toBeChecked();
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("link", { name: "Audit log", exact: true }).click();
  await expect(panel).toBeVisible();
  const leaving = page.waitForEvent("dialog");
  await page.evaluate(() => history.back());
  await (await leaving).dismiss();
  await expect(panel.getByLabel("Allow nothing")).toBeChecked();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Cache", exact: true }).click();
  await expect(page.getByText("Purge cache", { exact: true })).toBeVisible();
});
