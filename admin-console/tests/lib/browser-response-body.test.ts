import { afterEach, expect, test, vi } from "vitest";
import { browserApi, waitForBrowserResponses } from "@/lib/browser-api";

afterEach(() => vi.unstubAllGlobals());

test("transition waits until the complete response body has been consumed", async () => {
  let finish!: (body: object) => void;
  let started!: () => void;
  const reading = new Promise<void>((resolve) => {
    started = resolve;
  });
  const response = new Response("{}");
  vi.spyOn(response, "json").mockImplementation(() => {
    started();
    return new Promise((resolve) => {
      finish = resolve;
    });
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
  const events: string[] = [];
  const read = browserApi("/api/admin/orgs");
  const wait = waitForBrowserResponses()!.then(() => {
    events.push("drained");
  });
  await reading;
  await new Promise<void>((resolve) => setTimeout(resolve, 0));

  events.push("body completed");
  finish({});
  await read;
  await wait;

  expect(events).toEqual(["body completed", "drained"]);
});
