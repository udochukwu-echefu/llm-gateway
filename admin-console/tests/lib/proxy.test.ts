import { NextRequest } from "next/server";
import { expect, test, vi } from "vitest";
import { proxy } from "@/proxy";

const mocks = vi.hoisted(() => ({ origin: "https://console.example.test" }));
vi.mock("@/lib/config", () => ({
  readConfig: () => ({ ADMIN_CONSOLE_ORIGIN: mocks.origin }),
}));

test("proxy sends HSTS for an HTTPS console origin", async () => {
  mocks.origin = "https://console.example.test";

  const response = await proxy(new NextRequest("https://console.example.test/api/health"));

  expect(response.headers.get("Strict-Transport-Security")).toBe("max-age=31536000");
});

test("proxy omits HSTS for a local HTTP console origin", async () => {
  mocks.origin = "http://localhost:3100";

  const response = await proxy(new NextRequest("http://localhost:3100/api/health"));

  expect(response.headers.has("Strict-Transport-Security")).toBe(false);
});
