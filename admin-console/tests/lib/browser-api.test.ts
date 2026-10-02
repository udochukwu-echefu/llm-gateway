import { afterEach, expect, test, vi } from "vitest";
import { browserApi, waitForBrowserResponses } from "@/lib/browser-api";

afterEach(() => vi.unstubAllGlobals());

test("session changes wait for earlier response headers and their refreshed cookies", async () => {
  let finish!: (response: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    ),
  );
  const read = browserApi("/api/admin/orgs");
  let drained = false;
  const wait = waitForBrowserResponses()!.then(() => {
    drained = true;
  });

  expect(drained).toBe(false);
  finish(new Response("{}"));
  await read;
  await wait;

  expect(drained).toBe(true);
  expect(waitForBrowserResponses()).toBeUndefined();
});

test("failed reads cannot leave session transitions permanently waiting", async () => {
  let fail!: (error: Error) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((_resolve, reject) => {
          fail = reject;
        }),
    ),
  );
  const read = browserApi("/api/admin/orgs").catch(() => undefined);
  const wait = waitForBrowserResponses();

  fail(new Error("Offline"));
  await read;
  await wait;

  expect(waitForBrowserResponses()).toBeUndefined();
});
