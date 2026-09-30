import { afterEach, expect, test, vi } from "vitest";
import { adminRequest } from "@/lib/admin-client";
import { browserResponse } from "@/lib/bff-response";
afterEach(() => vi.unstubAllGlobals());
test("maps API envelope messages and preserves scoped 404", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { message: "Organization not found" } }), { status: 404 })));
  await expect(adminRequest("http://fake.test", "fake-key", "/orgs/other/teams")).rejects.toMatchObject({ status: 404, message: "Organization not found" });
});
test("unavailable upstream has a plain message without exception details", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("lgwa_fake-test-secret")));
  await expect(adminRequest("http://fake.test", "fake-key", "/orgs")).rejects.toMatchObject({ status: 503, message: "The gateway is unavailable. Please try again." });
});
test("no upstream credential text can be echoed to the browser", () => {
  const secret = "lgw_abcdefghijkl_" + "x".repeat(43);
  const result = browserResponse({ name: "lgwa_obviously-fake", key: secret, secret_hash: "hidden" }, false);
  expect(JSON.stringify(result).includes("lgwa_")).toBe(false);
  expect(JSON.stringify(result).includes(secret)).toBe(false);
  expect(JSON.stringify(browserResponse({ key: secret }, true)).includes(secret)).toBe(true);
});
test("request never follows redirects and authenticates only on the server", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("{}"));
  vi.stubGlobal("fetch", fetch);
  await adminRequest("http://fake.test", "fake-key", "/me");
  expect(fetch).toHaveBeenCalledWith("http://fake.test/admin/v1/me", expect.objectContaining({ cache: "no-store", redirect: "error", headers: expect.objectContaining({ Authorization: "Bearer fake-key" }) }));
});
