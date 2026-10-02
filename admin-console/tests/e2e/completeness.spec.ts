import { selectChoice } from "./fixtures";
import { test, expect, signIn } from "./fixtures";

test("requests-log filtering URL chips and complete attempt detail drawer", async ({
  page,
  credentials,
}) => {
  await signIn(page, credentials.platform);
  await page.goto("/requests?org=Demo%20Co&fallback=true&retried=true");
  await expect(page.getByRole("heading", { name: "Recorded attempts" })).toBeVisible();
  await page
    .getByRole("button", { name: /^demo-/ })
    .first()
    .click();
  await expect(page.getByRole("dialog", { name: "Request attempt timeline" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Attempt 1: groq 502" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Attempt 2: groq 502" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Attempt 3: deepseek 200" })).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const selectedRow = page.locator(".request-table tbody tr").first();
  const selectedId = await selectedRow.getByRole("button", { name: /^demo-/ }).innerText();
  await selectedRow.getByRole("cell").nth(2).click();
  await expect(page.getByRole("dialog", { name: "Request attempt timeline" })).toBeVisible();
  await expect(page.locator(".sheet-summary .copy-id")).toContainText(selectedId);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByText("Request filters", { exact: true }).click();
  await selectChoice(page.getByRole("combobox", { name: "Provider", exact: true }), "groq");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(/provider=groq/);
  await expect(page.getByText(/^No request results match/)).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("button", { name: /^demo-/ }).first()).toBeVisible();
});

test("CSV export contents match the current request and audit filters with rounded machine-readable numbers", async ({
  page,
  credentials,
}) => {
  await signIn(page, credentials.platform);
  const requestCsv = await page.evaluate(async () => ({
    status: 0,
    text: await (await fetch("/api/export/requests?org=Demo%20Co&provider=groq&status=5xx")).text(),
  }));
  expect(requestCsv.text).toContain('"request_id","created_at"');
  const lines = requestCsv.text.trim().split("\r\n");
  expect(lines.length).toBeGreaterThan(1);
  for (const line of lines.slice(1)) {
    expect(line).toContain('"groq"');
    expect(line).toContain('"502"');
  }
  const exact = await page.evaluate(async () => {
    const filter = "org=Demo%20Co&fallback=true&retried=true";
    const page = await (
      await fetch("/api/admin/orgs/Demo%20Co/requests?fallback=true&retried=true&page_size=1")
    ).json();
    const csv = await (await fetch(`/api/export/requests?${filter}`)).text();
    return { cost: page.data[0].cost_usd, csv };
  });
  expect(exact.csv.split("\r\n")[1].split('","')[18]).toBe(Number(exact.cost).toFixed(3));
  const auditCsv = await page.evaluate(
    async () => await (await fetch("/api/export/audit?action=set-models")).text(),
  );
  expect(auditCsv).toContain('"occurred_at"');
  expect(
    auditCsv
      .split("\r\n")
      .slice(1)
      .filter(Boolean)
      .every((line) => line.includes('"set-models"')),
  ).toBe(true);
  const invalid = await page.evaluate(
    async () => (await fetch("/api/export/requests?org=Demo%20Co&unknown=fake")).status,
  );
  expect(invalid).toBe(400);
});

test("analytics date range group switches and unknown first-byte gaps", async ({
  page,
  credentials,
}) => {
  await signIn(page, credentials.platform);
  await page.goto("/analytics?org=Demo%20Co");
  await page.getByRole("button", { name: "90 days", exact: true }).click();
  await expect(page).toHaveURL(/since=/);
  await selectChoice(page.getByRole("combobox", { name: "Group by", exact: true }), "provider");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(/group_by=provider/);
  await expect(page.getByRole("img", { name: /duration_p95/ })).toBeVisible();
  const latencyChart = page.getByRole("img", { name: /duration_p95/ });
  const maximum = Number(await latencyChart.getAttribute("data-axis-maximum"));
  const nvidia = page.getByRole("button", { name: "nvidia", exact: true });
  await expect(nvidia).toHaveAttribute("aria-pressed", "true");
  await nvidia.click();
  await expect(nvidia).toHaveAttribute("aria-pressed", "false");
  await expect
    .poll(async () => Number(await latencyChart.getAttribute("data-axis-maximum")))
    .toBeLessThan(maximum);
  await page.getByRole("checkbox", { name: "Log scale" }).check();
  await expect(latencyChart).toHaveAttribute("data-axis-scale", "log");
  await expect(latencyChart.getByText("1 ms", { exact: true })).toBeVisible();
  await nvidia.click();
  await selectChoice(
    page.getByRole("combobox", { name: "Chart measure", exact: true }),
    "ttfb_p95",
  );
  await expect(page.getByRole("img", { name: /ttfb_p95/ })).toBeVisible();
  await expect(
    page.getByText("Unknown values appear as gaps. Full values are in the table below."),
  ).toBeVisible();
  await selectChoice(page.getByRole("combobox", { name: "Group by", exact: true }), "team");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(/group_by=team/);
  await expect(page.locator("tbody tr").first()).toContainText(/Search|Support|Engineering/);
});

test("settings platform and org roles preferences persistence and forbidden API", async ({
  page,
  credentials,
}) => {
  await signIn(page, credentials.platform);
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Platform", exact: true })).toBeVisible();
  await selectChoice(page.getByRole("combobox", { name: "Table density", exact: true }), "compact");
  await selectChoice(
    page.getByRole("combobox", { name: "Default landing page", exact: true }),
    "/requests",
  );
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Table density", exact: true })).toHaveAttribute(
    "data-value",
    "compact",
  );
  await signIn(page, credentials.demoOrg);
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Account", exact: true })).toBeVisible();
  await expect(page.getByText("Northwind Health", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Platform", exact: true })).toHaveCount(0);
  expect(await page.evaluate(async () => (await fetch("/api/admin/settings")).status)).toBe(403);
});

test("keys search team status filters and last-used metadata", async ({ page, credentials }) => {
  await signIn(page, credentials.platform);
  await page.goto("/keys?org=Demo%20Co");
  await page.getByLabel("Search by name or key ID").fill("Synthetic Search");
  await selectChoice(page.getByRole("combobox", { name: "Key status", exact: true }), "expiring");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator("tbody tr")).toContainText("Expiring soon");
  await selectChoice(page.getByRole("combobox", { name: "Key status", exact: true }), "revoked");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.locator("tbody tr")).toContainText("Revoked");
  await selectChoice(page.getByRole("combobox", { name: "Key status", exact: true }), "never-used");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.locator("tbody tr").first()).toContainText("Never used");
});

test("audit filters action actor target dates URL and safe event drawer", async ({
  page,
  credentials,
}) => {
  await signIn(page, credentials.platform);
  await page.goto("/audit");
  await selectChoice(page.getByRole("combobox", { name: "Action", exact: true }), "set-models");
  await page.getByLabel("Actor", { exact: true }).fill("synthetic-demo-seeder");
  await selectChoice(page.getByRole("combobox", { name: "Target type", exact: true }), "team");
  await page.getByLabel("From date (UTC)").fill("2000-01-01");
  await page.getByLabel("To date (UTC)").fill("2099-01-01");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(/target_type=team/);
  await expect(page.locator("tbody tr").first()).toContainText("set-models");
  await page
    .getByRole("button", { name: /^Event \d/ })
    .first()
    .click();
  await expect(page.getByRole("dialog", { name: /Audit event/ })).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("synthetic-demo-seeder");
});

test("command palette page navigation and API-enforced organisation scoping", async ({
  page,
  credentials,
}) => {
  await signIn(page, credentials.platform);

  await page.getByRole("button", { name: "Search · ⌘/Ctrl K" }).click();
  await expect(page.getByRole("dialog", { name: "Go to…" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Search", exact: true })).toBeDisabled();
  await expect(page.locator(".search-orb")).toBeVisible();
  await expect(page.locator(".search-voice-band")).toBeVisible();
  await expect(page.locator(".search-voice[style]")).toHaveCount(0);
  await page.mouse.click(4, 4);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.keyboard.press("Control+k");
  await page.getByLabel("Search pages, organisations, teams and keys").fill("Northwind");
  await expect(
    page
      .getByRole("dialog")
      .getByRole("link", { name: /Northwind Health/ })
      .first(),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Search", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(
    page
      .getByRole("dialog")
      .getByRole("link", { name: /Northwind Health/ })
      .first(),
  ).toBeFocused();
  await page.getByLabel("Search pages, organisations, teams and keys").focus();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.keyboard.press("Control+k");
  await expect(page.getByLabel("Search pages, organisations, teams and keys")).toHaveValue("");
  await page.keyboard.press("Escape");
  await signIn(page, credentials.demoOrg);
  await page.keyboard.press("Control+k");
  await page.getByLabel("Search pages, organisations, teams and keys").fill("Demo Co");
  await expect
    .poll(async () =>
      page.evaluate(
        async () => (await (await fetch("/api/admin/search?q=Demo%20Co")).json()).data.length,
      ),
    )
    .toBe(0);
  await expect(page.getByRole("dialog").getByRole("link", { name: /Demo Co/ })).toHaveCount(0);
  await page.getByLabel("Search pages, organisations, teams and keys").fill("Requests");
  await page.getByRole("dialog").getByRole("link", { name: "Requests", exact: true }).click();
  await expect(page).toHaveURL(/requests/);
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
});
