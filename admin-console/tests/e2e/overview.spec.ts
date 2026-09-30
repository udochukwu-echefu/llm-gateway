import { test, expect, signIn, screenshot } from "./fixtures";
import { money } from "../../lib/money";
import { currentMonth } from "../../lib/usage-data";
import { sumDecimal } from "../../lib/overview-totals";
test("Overview landing numbers match the seeded org usage API and org scope", async ({
  page,
  context,
  credentials,
}) => {
  const month = new URLSearchParams(currentMonth());
  const response = await context.request.get(
    `http://127.0.0.1:18091/admin/v1/orgs/${encodeURIComponent(credentials.org)}/usage?${month}&group_by=team`,
    { headers: { Authorization: `Bearer ${credentials.orgKey}` } },
  );
  expect(response.status()).toBe(200);
  const rows = (await response.json()).data;
  const keysResponse = await context.request.get(
    `http://127.0.0.1:18091/admin/v1/orgs/${encodeURIComponent(credentials.org)}/keys?page_size=500`,
    { headers: { Authorization: `Bearer ${credentials.orgKey}` } },
  );
  const teamsResponse = await context.request.get(
    `http://127.0.0.1:18091/admin/v1/orgs/${encodeURIComponent(credentials.org)}/teams?page_size=500`,
    { headers: { Authorization: `Bearer ${credentials.orgKey}` } },
  );
  const keys = (await keysResponse.json()).data;
  const teams = (await teamsResponse.json()).data;
  await signIn(page, credentials.orgKey);
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByTestId("summary-requests")).toHaveText(
    rows
      .reduce((n: number, row: { requests: number }) => n + row.requests, 0)
      .toLocaleString("en-US"),
  );
  await expect(page.getByTestId("summary-spend")).toHaveText(
    money(sumDecimal(rows.map((row: { cost_usd: string | null }) => row.cost_usd))),
  );
  await expect(page.getByTestId("summary-tokens")).toHaveText(
    rows
      .reduce(
        (n: number, row: { prompt_tokens: number | null; completion_tokens: number | null }) =>
          n + (row.prompt_tokens ?? 0) + (row.completion_tokens ?? 0),
        0,
      )
      .toLocaleString("en-US"),
  );
  await expect(page.getByTestId("summary-savings")).toHaveText(
    money(
      sumDecimal(
        rows
          .filter((row: { cache_hits: number }) => row.cache_hits > 0)
          .map((row: { saved_usd: string | null }) => row.saved_usd),
      ),
    ),
  );
  await expect(page.getByTestId("summary-keys")).toHaveText(
    keys
      .filter(
        (key: { revoked_at: string | null; expires_at: string | null }) =>
          !key.revoked_at && (!key.expires_at || Date.parse(key.expires_at) > Date.now()),
      )
      .length.toLocaleString("en-US"),
  );
  await expect(page.getByTestId("summary-teams")).toHaveText(String(teams.length));
  await expect(page.getByRole("link", { name: new RegExp(credentials.org) }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: new RegExp(credentials.other) })).toHaveCount(0);
  await expect(page.getByText(/unpriced requests$/)).toBeVisible();
  await screenshot(page, "overview-org");
});
test("Overview platform landing includes all organisations and recent activity", async ({
  page,
  credentials,
}) => {
  await signIn(page, credentials.platform);
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole("link", { name: new RegExp(credentials.org) }).first()).toBeVisible();
  await expect(
    page.getByRole("link", { name: new RegExp(credentials.other) }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Recent audit events", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "View full audit log →", exact: true }),
  ).toBeVisible();
  await screenshot(page, "overview");
  await page.getByLabel("Theme", { exact: true }).selectOption("dark");
  await screenshot(page, "overview-dark");
  await page.setViewportSize({ width: 820, height: 1100 });
  await screenshot(page, "overview-tablet");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});
