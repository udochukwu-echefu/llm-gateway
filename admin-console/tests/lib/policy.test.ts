import { expect, test } from "vitest";
import { hasSameOrigin } from "@/lib/origin";
import { readConfig } from "@/lib/config";
import { budgetSchema, limitsSchema, nameSchema, operationSchema } from "@/lib/bff-policy";
import { budgetPercent, money, pico } from "@/lib/money";
import { submissionId } from "@/lib/submission";
test("Origin is mandatory and matches configured origin including scheme and port", () => {
  const request = (origin?: string) =>
    new Request("https://console.test/api", {
      method: "POST",
      headers: origin ? { origin, host: "evil.test" } : {},
    });
  expect(hasSameOrigin(request("https://console.test"), "https://console.test")).toBe(true);
  for (const origin of [
    undefined,
    "https://evil.test",
    "http://console.test",
    "https://console.test:444",
    "null",
  ])
    expect(hasSameOrigin(request(origin), "https://console.test")).toBe(false);
});
test("settings fail closed without printing supplied secrets", () => {
  expect(() => readConfig({ ADMIN_CONSOLE_SESSION_SECRET: "short" })).toThrow(
    "Invalid console configuration",
  );
  expect(() =>
    readConfig({
      ADMIN_API_URL: "http://user:password@fake.test",
      ADMIN_CONSOLE_ORIGIN: "https://console.test",
      ADMIN_CONSOLE_SESSION_SECRET: "obviously-fake-test-secret-at-least-32-bytes",
    }),
  ).toThrow("Invalid console configuration");
});
test("money is formatted and compared exactly from decimal strings", () => {
  expect(money("1234567.000000000001")).toBe("$1,234,567.00");
  expect(money("0E-12")).toBe("$0.00");
  expect(money("1E-12")).toBe("$0.000000000001");
  expect(money("0.1")).toBe("$0.10");
  expect(money(null)).toBe("Unpriced");
  expect(pico("0.1") + pico("0.2")).toBe(pico("0.3"));
  expect(budgetPercent("0.1", "0.3")).toBe(33);
  expect(budgetPercent("2", "1")).toBe(100);
});
test("same submission and retry use one ID; a later submission uses another", () => {
  const submission = submissionId();
  const first = submission.begin();
  expect(submission.begin()).toBe(first);
  submission.finish();
  expect(submission.begin()).not.toBe(first);
});
test("BFF permits only the specified screens and validates mutations", () => {
  expect(operationSchema("PUT", "/orgs/fake/catalog")).toBeUndefined();
  expect(operationSchema("POST", "/orgs")).toBeDefined();
  for (const name of ["fake/team", ".", ".."])
    expect(nameSchema.safeParse({ name }).success).toBe(false);
  expect(nameSchema.safeParse({ name: "Fake%?#\\ workspace" }).success).toBe(true);
  expect(limitsSchema.safeParse({ rpm: -1, tpm: null, max_concurrency: null }).success).toBe(false);
  expect(budgetSchema.safeParse({ usd: "0.1", alert_at: "0.8" }).success).toBe(true);
  for (const usd of [0.1, "NaN", "1e3", "9223372.036854775808"])
    expect(budgetSchema.safeParse({ usd, alert_at: "0.8" }).success).toBe(false);
});
