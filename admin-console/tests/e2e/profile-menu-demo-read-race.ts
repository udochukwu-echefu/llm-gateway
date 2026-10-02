import { test, expect } from "./fixtures";
import { actions, explore, open, trigger, assertNorthwind } from "./profile-menu-demo-controls";

export function profileMenuReadRaceTests() {
  test("switch waits for an earlier authenticated read so its old cookie cannot restore platform scope", async ({
    page,
  }) => {
    await explore(page);
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let reading = false;
    await page.route("**/api/admin/orgs/Demo%20Co/teams?*", async (route) => {
      reading = true;
      await gate;
      await route.fallback();
    });
    await page.goto("/orgs/Demo%20Co");
    await expect.poll(() => reading).toBe(true);
    let switching = false;
    page.on("request", (request) => {
      if (request.url().endsWith("/api/auth/demo")) switching = true;
    });
    await open(page);
    const choice = actions(page).getByRole("button", { name: /^Northwind Health viewer/ });

    await choice.click();

    await expect(choice).toBeDisabled();
    await expect(choice).toContainText("Switching…");
    expect(switching).toBe(false);
    release();
    await expect(trigger(page)).toHaveAttribute(
      "aria-label",
      "Profile menu: Northwind Health viewer",
    );
    await page.waitForLoadState("networkidle");
    await assertNorthwind(page);
    await page.reload();
    await assertNorthwind(page);
  });
}
