import { test, expect, signIn } from "./fixtures";

test("normal console profile controls preserve search, appearance and authentication", async ({
  page,
  credentials,
}) => {
  await signIn(page, credentials.platform);
  const trigger = page.getByRole("button", { name: /^Profile menu:/ });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const actions = page.getByRole("region", { name: "Profile actions" });
  await expect(actions).toBeVisible();
  await expect(actions.getByRole("region", { name: "Demo profiles" })).toHaveCount(0);
  await expect(actions.getByRole("link", { name: "Requests" })).toHaveAttribute(
    "href",
    "/requests",
  );
  await page.keyboard.press("Tab");
  await expect(actions.getByRole("link", { name: "View profile" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await expect(actions).not.toBeVisible();

  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog", { name: "Go to…" })).toBeVisible();
  await page.keyboard.press("Escape");
  await trigger.click();
  await actions.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(page.getByRole("button", { name: "Switch to light theme" })).toBeVisible();
  await actions.getByRole("link", { name: "View profile" }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole("combobox", { name: "Theme", exact: true })).toHaveAttribute(
    "data-value",
    "dark",
  );
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await trigger.click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel("Admin API key")).toBeVisible();
});

test("profile logout and navigation cannot discard an unsaved normal-console policy without consent", async ({
  page,
  credentials,
}) => {
  await signIn(page, credentials.orgKey);
  await page.goto(`/orgs/${encodeURIComponent(credentials.org)}`);
  await page.getByRole("button", { name: "Policies", exact: true }).click();
  const panel = page.getByRole("region", { name: "Model policy", exact: true });
  await panel.getByLabel("Allow nothing").check();
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/auth/logout")) requests.push(request.method());
  });
  await page.getByRole("button", { name: /^Profile menu:/ }).click();
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(panel.getByLabel("Allow nothing")).toBeChecked();
  expect(requests).toEqual([]);
  page.once("dialog", (dialog) => dialog.dismiss());
  await page
    .getByRole("region", { name: "Profile actions" })
    .getByRole("link", { name: "Requests" })
    .click();
  await expect(panel.getByLabel("Allow nothing")).toBeChecked();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(requests).toEqual(["POST"]);
});
