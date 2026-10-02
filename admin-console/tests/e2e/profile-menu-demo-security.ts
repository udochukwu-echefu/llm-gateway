import { test, expect } from "./fixtures";
import { actions, explore, open, trigger } from "./profile-menu-demo-controls";

export function profileMenuDemoSecurityTests() {
  test("demo auth switching preserves Origin checks, private cookies and nonce CSP", async ({
    page,
    context,
  }) => {
    const response = await page.goto("/login");
    const csp = response!.headers()["content-security-policy"];
    expect(csp).toMatch(/script-src[^;]*'nonce-[^']+'/);
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).not.toContain("unsafe-inline");
    expect(csp).not.toContain("unsafe-eval");
    await explore(page);
    const cookie = (await context.cookies()).find((item) => item.name === "__Host-lgw-console")!;
    expect(cookie.httpOnly).toBe(true);
    expect(cookie.secure).toBe(true);
    expect(cookie.sameSite).toBe("Strict");
    expect(await page.evaluate(() => document.cookie)).not.toContain("lgw-console");
    for (const origin of ["https://evil.invalid", undefined]) {
      const result = await context.request.post("/api/auth/demo", {
        headers: origin ? { Origin: origin } : {},
        data: { as: "org" },
      });
      expect(result.status()).toBe(403);
      expect(result.headers()["cache-control"]).toBe("no-store");
      expect((await result.json()).error).toBe("Request origin is not allowed.");
    }
    await page.reload();
    await expect(trigger(page)).toHaveAttribute("aria-label", "Profile menu: Platform viewer");
  });

  test("real sign-in quota returns 429 without replacing the current authenticated viewer", async ({
    page,
  }) => {
    await explore(page);
    const results = await page.evaluate(async () => {
      const replies = [];
      for (let index = 0; index < 11; index++) {
        const response = await fetch("/api/auth/demo", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ as: "invalid" }),
        });
        replies.push({
          status: response.status,
          retry: response.headers.get("Retry-After"),
          error: (await response.json()).error,
        });
      }
      return replies;
    });
    for (const result of results) expect([400, 429]).toContain(result.status);
    const last = results.at(-1)!;
    expect(last.status).toBe(429);
    expect(last.error).toBe("Too many sign-in attempts. Please try again in a minute.");
    expect(Number(last.retry)).toBeGreaterThan(0);
    await page.reload();
    await expect(trigger(page)).toHaveAttribute("aria-label", "Profile menu: Platform viewer");
    await open(page);
    await expect(actions(page).getByRole("button", { name: /^Platform viewer/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const organisations = await page.evaluate(async () => (await fetch("/api/admin/orgs")).status);
    expect(organisations).toBe(200);
  });
}
