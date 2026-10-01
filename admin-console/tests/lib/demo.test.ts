import { beforeEach, expect, test, vi } from "vitest";
import { NextRequest } from "next/server";
import { readConfig } from "@/lib/config-schema.mjs";
import { checkDemoKeys } from "@/lib/demo-role.mjs";
import { POST as demo } from "@/app/api/auth/demo/route";
import { POST as login } from "@/app/api/auth/login/route";
import { POST, PUT, DELETE } from "@/app/api/admin/[...path]/route";
import { isActive, DEMO_ABSOLUTE_MS, sessionOptions } from "@/lib/session-policy";

const mocks = vi.hoisted(() => ({
  config: {
    ADMIN_API_URL: "http://fake.test",
    ADMIN_CONSOLE_ORIGIN: "https://console.test",
    ADMIN_CONSOLE_SESSION_SECRET: "fake-session-secret-at-least-32-bytes",
    ADMIN_CONSOLE_TRUSTED_PROXY_HOPS: 0,
    DEMO_MODE: true,
    DEMO_ALLOW_KEY_SIGN_IN: false,
    DEMO_VIEWER_KEY: "lgwa_abcdefghijkl_" + "a".repeat(43),
    DEMO_ORG_VIEWER_KEY: "lgwa_bcdefghijklm_" + "b".repeat(43),
  },
  session: {
    adminKey: "fake",
    identity: { key_id: "fake", name: "Demo viewer", role: "viewer", organization: null },
    demo: true,
    issuedAt: 1,
    lastSeen: 1,
    destroy: vi.fn(),
    save: vi.fn(),
  },
  identity: vi.fn(),
  request: vi.fn(),
}));
vi.mock("@/lib/config", () => ({ readConfig: () => mocks.config }));
vi.mock("@/lib/session", () => ({ readSession: async () => mocks.session }));
vi.mock("@/lib/identity", () => ({ fetchIdentity: mocks.identity }));
vi.mock("@/lib/admin-client", async (original) => ({
  ...(await original<typeof import("@/lib/admin-client")>()),
  adminRequest: mocks.request,
}));
beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  mocks.config.DEMO_MODE = true;
  mocks.config.DEMO_ALLOW_KEY_SIGN_IN = false;
  mocks.session.issuedAt = Date.now();
  mocks.session.lastSeen = Date.now();
  mocks.identity.mockResolvedValue(mocks.session.identity);
});
function request(
  body: unknown = { as: "platform" },
  origin: string | null = "https://console.test",
  client = crypto.randomUUID(),
) {
  return new NextRequest("https://console.test/api/auth/demo", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { ...(origin ? { Origin: origin } : {}), "x-console-client-address": client },
  });
}
test("demo config requires valid booleans and viewer key without exposing values", () => {
  expect(
    readConfig({
      ...mocks.config,
      ADMIN_CONSOLE_TRUSTED_PROXY_HOPS: "0",
      DEMO_MODE: "true",
      DEMO_ALLOW_KEY_SIGN_IN: "false",
    }).DEMO_MODE,
  ).toBe(true);
  for (const env of [
    { DEMO_MODE: "true", DEMO_VIEWER_KEY: undefined },
    { DEMO_MODE: "1" },
    { DEMO_ORG_VIEWER_KEY: "not-a-key" },
  ]) {
    expect(() =>
      readConfig({
        ADMIN_API_URL: "http://fake.test",
        ADMIN_CONSOLE_ORIGIN: "https://console.test",
        ADMIN_CONSOLE_SESSION_SECRET: "fake-session-secret-at-least-32-bytes",
        ...env,
      }),
    ).toThrow("Invalid console configuration");
  }
  expect(
    readConfig({
      ADMIN_API_URL: "http://fake.test",
      ADMIN_CONSOLE_ORIGIN: "https://console.test",
      ADMIN_CONSOLE_SESSION_SECRET: "fake-session-secret-at-least-32-bytes",
    }).DEMO_MODE,
  ).toBe(false);
});
test("startup refuses a platform-admin demo key and wrong viewer scope", async () => {
  for (const identity of [
    { role: "platform", organization: null },
    { role: "viewer", organization: { id: "fake", name: "Northwind Health" } },
    {},
  ]) {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(identity)));
    await expect(
      checkDemoKeys({ ...mocks.config, DEMO_ORG_VIEWER_KEY: undefined }),
    ).rejects.toThrow("Demo startup refused");
  }
});
test("startup checks both demo scopes and refuses outages without credential text", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ role: "viewer", organization: null }))
    .mockResolvedValueOnce(
      Response.json({ role: "viewer", organization: { id: "fake", name: "Northwind Health" } }),
    );
  vi.stubGlobal("fetch", fetcher);
  await checkDemoKeys(mocks.config);
  expect(fetcher).toHaveBeenCalledTimes(2);
  fetcher.mockRejectedValue(new Error(mocks.config.DEMO_VIEWER_KEY));
  await expect(checkDemoKeys(mocks.config)).rejects.toThrow("Demo startup refused");
  mocks.config.DEMO_MODE = false;
  fetcher.mockClear();
  await checkDemoKeys(mocks.config);
  expect(fetcher).not.toHaveBeenCalled();
});
test("demo route is 404 when demo mode is off", async () => {
  mocks.config.DEMO_MODE = false;
  expect((await demo(request())).status).toBe(404);
  expect(mocks.identity).not.toHaveBeenCalled();
});
test("demo sign-in rejects missing and cross-site Origin", async () => {
  for (const origin of [null, "https://evil.test"])
    expect((await demo(request(undefined, origin))).status).toBe(403);
  expect(mocks.identity).not.toHaveBeenCalled();
});
test("demo sign-in uses a server-side key and returns only identity", async () => {
  const response = await demo(request());
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({ identity: mocks.session.identity });
  expect(mocks.identity).toHaveBeenCalledWith("http://fake.test", mocks.config.DEMO_VIEWER_KEY);
  expect(mocks.session.demo).toBe(true);
  expect(mocks.session.save).toHaveBeenCalledOnce();
});
test("demo sign-in refuses a changed admin role", async () => {
  mocks.identity.mockResolvedValue({ ...mocks.session.identity, role: "platform" });
  expect((await demo(request())).status).toBe(503);
  expect(mocks.session.save).not.toHaveBeenCalled();
});
test("demo sign-in throttles each client including successful sign-ins", async () => {
  const client = crypto.randomUUID();
  for (let count = 0; count < 10; count++)
    expect((await demo(request({ as: "platform" }, undefined, client))).status).toBe(200);
  const blocked = await demo(request({ as: "platform" }, undefined, client));
  expect(blocked.status).toBe(429);
  expect(blocked.headers.get("Retry-After")).toBeTruthy();
  expect((await demo(request())).status).toBe(200);
});
test("key sign-in is 404 by default in demo mode", async () => {
  expect((await login(request({ key: "fake" }))).status).toBe(404);
  expect(mocks.identity).not.toHaveBeenCalled();
});
test("explicitly enabled key sign-in uses the demo session lifetime", async () => {
  mocks.config.DEMO_ALLOW_KEY_SIGN_IN = true;
  mocks.session.demo = false;
  const response = await login(request({ key: mocks.config.DEMO_VIEWER_KEY }));
  expect(response.status).toBe(200);
  expect(mocks.session.demo).toBe(true);
  expect(mocks.session.save).toHaveBeenCalledOnce();
});
test("viewer BFF mutations fail before parsing bodies or accessing gateway", async () => {
  for (const handler of [POST, PUT, DELETE]) {
    const method = handler === PUT ? "PUT" : handler === DELETE ? "DELETE" : "POST";
    const req = new NextRequest("https://console.test/api/admin/orgs", {
      method,
      headers: { Origin: "https://console.test" },
      body: "malformed",
    });
    const path = method === "POST" ? ["orgs"] : ["orgs", "Own", "model-policy"];
    const response = await handler(req, { params: Promise.resolve({ path }) });
    expect(response.status).toBe(403);
    expect((await response.json()).code).toBe("read_only_admin");
  }
  expect(mocks.request).not.toHaveBeenCalled();
});
test("demo sessions enforce two-hour absolute and thirty-minute idle boundaries", () => {
  const issued = 100000;
  const identity = { ...mocks.session.identity, role: "viewer" as const };
  const active = {
    adminKey: "fake",
    identity,
    demo: true,
    issuedAt: issued,
    lastSeen: issued + DEMO_ABSOLUTE_MS - 1,
  };
  expect(isActive(active, issued + DEMO_ABSOLUTE_MS - 1)).toBe(true);
  expect(isActive(active, issued + DEMO_ABSOLUTE_MS)).toBe(false);
  expect(isActive({ ...active, lastSeen: issued }, issued + 30 * 60 * 1000)).toBe(false);
  expect(sessionOptions("fake", true).cookieOptions?.maxAge).toBe(7200);
});
