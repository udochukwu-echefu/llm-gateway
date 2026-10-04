import type { Page, Request, Response } from "@playwright/test";
import { expect, test } from "vitest";
import { responseScanner } from "../e2e/no-leak";

function stubPage() {
  let onResponse: ((response: Response) => void) | undefined;
  const page = {
    on(_event: string, listener: (response: Response) => void) {
      onResponse = listener;
    },
    async route() {},
    async evaluate() {},
  } as unknown as Page;
  return {
    page,
    emit(response: Response) {
      if (!onResponse) throw new Error("Response scanner was not attached");
      onResponse(response);
    },
  };
}

function stubResponse(body: () => Promise<Buffer>) {
  const request = { method: () => "GET" } as Request;
  return {
    request: () => request,
    url: () => "http://localhost/test-response",
    body,
    allHeaders: async () => ({}),
  } as Response;
}

test("settle waits for a browser response body before navigation", async () => {
  const { page, emit } = stubPage();
  const scanner = await responseScanner(page);
  let finish!: (body: Buffer) => void;
  const body = new Promise<Buffer>((resolve) => {
    finish = resolve;
  });
  emit(stubResponse(() => body));
  let settled = false;
  const waiting = scanner.settle().then(() => {
    settled = true;
  });
  await Promise.resolve();

  expect(settled).toBe(false);
  finish(Buffer.from("safe response"));
  await waiting;

  expect(settled).toBe(true);
  await expect(scanner.verify([], [])).resolves.toEqual({ responses: 1, permitted: 0 });
});

test("an uncapturable browser response still fails the no-leak scan", async () => {
  const { page, emit } = stubPage();
  const scanner = await responseScanner(page);
  emit(
    stubResponse(async () => {
      throw new Error("response body evicted before capture");
    }),
  );

  await expect(scanner.verify([], [])).rejects.toThrow("Every browser response must be inspected");
});
