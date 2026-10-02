import { afterEach, expect, test, vi } from "vitest";

afterEach(() => vi.unstubAllGlobals());

test("failed session change resumes deferred reads with the unchanged session", async () => {
  vi.resetModules();
  const { browserApi, browserSessionApi } = await import("@/lib/browser-api");
  let finish!: (response: Response) => void;
  const fetch = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValue(new Response("{}"));
  vi.stubGlobal("fetch", fetch);
  const change = browserSessionApi("/api/auth/demo", { method: "POST" }).catch(() => undefined);
  const read = browserApi("/api/admin/orgs");
  expect(fetch).toHaveBeenCalledTimes(1);

  finish(new Response('{"error":"Unavailable"}', { status: 503 }));
  await change;
  await read;

  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch.mock.calls[1][0]).toBe("/api/admin/orgs");
});

test("successful session change sends no queued old-document reads before navigation", async () => {
  vi.resetModules();
  const { browserApi, browserSessionApi } = await import("@/lib/browser-api");
  const fetch = vi.fn().mockResolvedValue(new Response("{}"));
  vi.stubGlobal("fetch", fetch);
  const change = browserSessionApi("/api/auth/demo", { method: "POST" });
  void browserApi("/api/admin/orgs");

  await change;
  await new Promise<void>((resolve) => setTimeout(resolve, 0));

  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toBe("/api/auth/demo");
});
