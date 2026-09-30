import { expect, test, vi } from "vitest";
import { LoginThrottle } from "@/lib/login-throttle";
import { clientAddress } from "../../scripts/client-address.mjs";

test("login failures are isolated by client and expire without extending the window", () => {
  const throttle = new LoginThrottle(2, 60000);
  throttle.failed("fake-client-a", 1000);
  throttle.failed("fake-client-a", 2000);
  expect(throttle.retryAfter("fake-client-a", 3000)).toBe(58);
  expect(throttle.retryAfter("fake-client-b", 3000)).toBe(0);
  expect(throttle.retryAfter("fake-client-a", 61000)).toBe(0);
  throttle.failed("fake-client-b", 61000);
  throttle.succeeded("fake-client-b");
  expect(throttle.retryAfter("fake-client-b", 61001)).toBe(0);
});

test("client-supplied forwarded IP is ignored unless proxy hops are explicitly trusted", () => {
  expect(clientAddress("127.0.0.1", "198.51.100.8")).toBe("127.0.0.1");
  expect(clientAddress("::ffff:127.0.0.1", "198.51.100.8")).toBe("127.0.0.1");
  expect(clientAddress("127.0.0.1", "spoofed, 198.51.100.8, 192.0.2.10", 2))
    .toBe("198.51.100.8");
  expect(clientAddress("127.0.0.1", "invalid", 1)).toBe("127.0.0.1");
  expect(clientAddress("127.0.0.1", "198.51.100.8", 2)).toBe("127.0.0.1");
});

vi.mock("@/lib/config", () => ({ readConfig: () => ({
  ADMIN_API_URL: "http://fake.test", ADMIN_CONSOLE_ORIGIN: "https://console.test",
}) }));
vi.mock("@/lib/identity", () => ({ fetchIdentity: vi.fn() }));

test("login HTTP handler throttles the abusive client before forwarding another guess", async () => {
  const { POST } = await import("@/app/api/auth/login/route");
  const { fetchIdentity } = await import("@/lib/identity");
  const request = () => new Request("https://console.test/api/auth/login", {
    method: "POST", headers: {
      Origin: "https://console.test", "Content-Type": "application/json",
      "x-console-client-address": "fake-abusive-client",
    }, body: JSON.stringify({ key: "fake-malformed" }),
  });
  for (let i = 0; i < 10; i++) expect((await POST(request())).status).toBe(400);
  const denied = await POST(request());
  expect(denied.status).toBe(429);
  expect((await denied.json()).error).toBe(
    "Too many sign-in attempts. Please try again in a minute.",
  );
  expect(fetchIdentity).not.toHaveBeenCalled();
});
