import { beforeEach, expect, test, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST as login } from "@/app/api/auth/login/route";
import { POST as logout } from "@/app/api/auth/logout/route";
import { POST, PUT, DELETE, GET } from "@/app/api/admin/[...path]/route";
import { AdminApiError } from "@/lib/admin-client";
const mocks = vi.hoisted(() => ({
  session: {
    adminKey: "fake",
    identity: {
      key_id: "fakeid",
      name: "Fake",
      role: "org",
      organization: { id: "fakeorg", name: "Own" },
    },
    issuedAt: 0,
    lastSeen: 0,
    destroy: vi.fn(),
    save: vi.fn(),
  },
  request: vi.fn(),
  identity: vi.fn(),
}));
vi.mock("@/lib/config", () => ({
  readConfig: () => ({
    ADMIN_API_URL: "http://fake.test",
    ADMIN_CONSOLE_ORIGIN: "https://console.test",
  }),
}));
vi.mock("@/lib/session", () => ({ readSession: async () => mocks.session }));
vi.mock("@/lib/admin-client", async (original) => ({
  ...(await original<typeof import("@/lib/admin-client")>()),
  adminRequest: mocks.request,
}));
vi.mock("@/lib/identity", () => ({ fetchIdentity: mocks.identity }));
beforeEach(() => {
  vi.clearAllMocks();
  mocks.request.mockReset();
  mocks.session.issuedAt = Date.now();
  mocks.session.lastSeen = Date.now();
  mocks.request.mockResolvedValue({ updated: true });
  mocks.session.save.mockResolvedValue(undefined);
});
function request(
  method: string,
  origin: string | undefined = "https://console.test",
  body?: object,
) {
  return new NextRequest("https://console.test/api/admin/orgs/Own/teams/test/limits", {
    method,
    headers: {
      ...(origin && { Origin: origin }),
      "Content-Type": "application/json",
      "Idempotency-Key": "00000000-0000-4000-8000-000000000000",
    },
    body: body && JSON.stringify(body),
  });
}
const limits = { params: Promise.resolve({ path: ["orgs", "Own", "teams", "test", "limits"] }) };
test("mutating HTTP handlers reject cross-origin and missing Origin before any mutation", async () => {
  for (const origin of ["https://evil.test", undefined]) {
    // Explicitly remove Origin for the missing-header case.
    const make = (method: string, body?: object) => {
      const req = request(method, origin, body);
      if (!origin) req.headers.delete("Origin");
      return req;
    };
    expect((await login(make("POST", { key: "fake" }))).status).toBe(403);
    expect((await logout(make("POST"))).status).toBe(403);
    expect(
      (await POST(make("POST", { name: "fake" }), { params: Promise.resolve({ path: ["orgs"] }) }))
        .status,
    ).toBe(403);
    expect(
      (await PUT(make("PUT", { rpm: 1, tpm: null, max_concurrency: null }), limits)).status,
    ).toBe(403);
    expect((await DELETE(make("DELETE"), limits)).status).toBe(403);
  }
  expect(mocks.request).not.toHaveBeenCalled();
  expect(mocks.session.destroy).not.toHaveBeenCalled();
});
test("valid BFF mutation forwards the original key and scope unchanged", async () => {
  const response = await PUT(
    request("PUT", "https://console.test", { rpm: 5, tpm: null, max_concurrency: null }),
    limits,
  );
  expect(response.status).toBe(200);
  expect(mocks.request).toHaveBeenCalledWith(
    "http://fake.test",
    "fake",
    "/orgs/Own/teams/test/limits",
    expect.objectContaining({ method: "PUT" }),
  );
});
test("gateway 401 destroys the session; scoped 404 remains not found", async () => {
  mocks.request.mockRejectedValue(new AdminApiError(401, "Invalid admin API key."));
  expect((await GET(request("GET"), limits)).status).toBe(401);
  expect(mocks.session.destroy).toHaveBeenCalledOnce();
  mocks.session.destroy.mockClear();
  mocks.request.mockRejectedValue(new AdminApiError(404, "Organization not found"));
  const response = await GET(request("GET"), limits);
  expect(response.status).toBe(404);
  expect((await response.json()).error).toBe("Organization not found");
  expect(mocks.session.destroy).not.toHaveBeenCalled();
});
test("idle-expired session is destroyed before upstream access", async () => {
  mocks.session.lastSeen = Date.now() - 30 * 60 * 1000;
  expect((await GET(request("GET"), limits)).status).toBe(401);
  expect(mocks.session.destroy).toHaveBeenCalledOnce();
  expect(mocks.request).not.toHaveBeenCalled();
});
test("encoded slashes and traversal cannot escape a BFF path segment", async () => {
  for (const part of ["..", "a%2Fb", "bad%ZZ"]) {
    const response = await GET(request("GET"), {
      params: Promise.resolve({ path: ["orgs", part, "teams"] }),
    });
    expect(response.status).toBe(404);
  }
  expect(mocks.request).not.toHaveBeenCalled();
});

test("literal percent, query and fragment characters keep the resource scope", async () => {
  const response = await GET(request("GET"), {
    params: Promise.resolve({ path: ["orgs", "Fake%25%3F%23%5C", "teams"] }),
  });
  expect(response.status).toBe(200);
  expect(mocks.request).toHaveBeenCalledWith(
    "http://fake.test",
    "fake",
    "/orgs/Fake%25%3F%23%5C/teams",
    expect.anything(),
  );
});

for (const kind of ["model-policy", "guardrails", "residency"])
  test(`BFF forwards If-Match only for ${kind} writes`, async () => {
    const req = request("DELETE");
    const version = '"' + "a".repeat(64) + '"';
    req.headers.set("If-Match", version);
    const response = await DELETE(req, {
      params: Promise.resolve({ path: ["orgs", "Own", kind] }),
    });
    expect(response.status).toBe(200);
    expect(mocks.request).toHaveBeenCalledWith(
      "http://fake.test",
      "fake",
      `/orgs/Own/${kind}`,
      expect.objectContaining({ headers: { "If-Match": version } }),
    );
  });
test("BFF rejects missing and malformed conditional headers before mutation", async () => {
  for (const header of [null, "bad", "*"]) {
    const req = request("DELETE");
    if (header) req.headers.set("If-Match", header);
    expect(
      (await DELETE(req, { params: Promise.resolve({ path: ["orgs", "Own", "residency"] }) }))
        .status,
    ).toBe(400);
  }
  expect(mocks.request).not.toHaveBeenCalled();
});
test("BFF does not forward If-Match on nonpolicy mutations", async () => {
  const req = request("DELETE");
  req.headers.set("If-Match", '"' + "a".repeat(64) + '"');
  expect((await DELETE(req, limits)).status).toBe(200);
  expect(mocks.request.mock.calls[0][3].headers).toEqual({});
});

for (const source of ["regions field", "model regions"] as const)
  test(`residency BFF validates against upstream catalogue ${source}`, async () => {
    const catalog =
      source === "regions field"
        ? { models: [], aliases: {}, regions: ["test-region", "unknown"] }
        : { models: [{ region: "test-region" }], aliases: {} };
    mocks.request.mockResolvedValueOnce(catalog).mockResolvedValueOnce({ updated: true });
    const req = request("PUT", "https://console.test", { regions: ["test-region", "test-region"] });
    req.headers.set("If-Match", '"' + "a".repeat(64) + '"');
    const response = await PUT(req, {
      params: Promise.resolve({ path: ["orgs", "Own", "residency"] }),
    });
    expect(response.status).toBe(200);
    expect(mocks.request.mock.calls[0]).toEqual(["http://fake.test", "fake", "/catalog"]);
    expect(mocks.request.mock.calls[1][2]).toBe("/orgs/Own/residency");
    expect(JSON.parse(mocks.request.mock.calls[1][3].body)).toEqual({ regions: ["test-region"] });
  });
test("residency BFF rejects unadvertised regions before any policy mutation", async () => {
  mocks.request.mockResolvedValueOnce({
    models: [],
    aliases: {},
    regions: ["test-region", "unknown"],
  });
  const req = request("PUT", "https://console.test", { regions: ["eu"] });
  req.headers.set("If-Match", '"' + "a".repeat(64) + '"');
  const response = await PUT(req, {
    params: Promise.resolve({ path: ["orgs", "Own", "residency"] }),
  });
  expect(response.status).toBe(400);
  expect(mocks.request).toHaveBeenCalledOnce();
  expect(mocks.request.mock.calls[0][2]).toBe("/catalog");
});
test("residency BFF does not mutate when the catalogue is unavailable", async () => {
  mocks.request.mockRejectedValueOnce(new AdminApiError(503, "Gateway unavailable"));
  const req = request("PUT", "https://console.test", { regions: ["eu"] });
  req.headers.set("If-Match", '"' + "a".repeat(64) + '"');
  const response = await PUT(req, {
    params: Promise.resolve({ path: ["orgs", "Own", "residency"] }),
  });
  expect(response.status).toBe(503);
  expect(mocks.request).toHaveBeenCalledOnce();
});
