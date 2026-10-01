import { test, expect, signIn } from "./fixtures";
test("empty workspace guides first team key request and unmatched audit filter", async ({
  page,
  credentials,
}) => {
  await signIn(page, credentials.platform);
  await page.goto("/orgs");
  await page.getByLabel("Organisation name").fill("Empty synthetic workspace");
  await page.getByText("Create organisation", { exact: true }).click();
  await page.getByRole("link", { name: "Empty synthetic workspace", exact: true }).click();
  await expect(page.getByText(/^Create your first team/)).toBeVisible();
  await expect(page.getByLabel("Team name")).toBeVisible();
  await expect(page.getByRole("heading", { name: "No usage yet", exact: true })).toBeVisible();
  await expect(page.locator(".request-example")).toContainText("YOUR_TEAM_API_KEY");
  await page.getByLabel("Team name").fill("Empty team");
  await page.getByText("Create team", { exact: true }).click();
  await page.getByRole("link", { name: "Empty team", exact: true }).click();
  await expect(page.getByText(/^No keys match this filter/)).toBeVisible();
  await expect(page.getByLabel("Key name")).toBeVisible();
  await page.goto("/audit?action=obviously-fake-no-matching-action");
  await expect(page.getByText(/^No audit results match this filter/)).toBeVisible();
});
