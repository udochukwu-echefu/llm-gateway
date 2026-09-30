import { afterEach, expect, test, vi } from "vitest";
import { allPages, currentMonth } from "@/lib/usage-data";
afterEach(() => vi.unstubAllGlobals());
test("reports use the current UTC month including leap years", () => {
  expect(currentMonth(new Date("2024-02-29T23:59:00Z"))).toEqual({
    since: "2024-02-01",
    until: "2024-02-29",
  });
  expect(currentMonth(new Date("2026-01-01T00:01:00Z"))).toEqual({
    since: "2026-01-01",
    until: "2026-01-31",
  });
});
test("usage aggregation follows every API cursor before showing totals", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ data: [{ group: "first" }], next_cursor: "model/next" })),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ data: [{ group: "last" }], next_cursor: null })),
    );
  vi.stubGlobal("fetch", fetch);
  expect(await allPages("/api/admin/orgs/fake/usage?group_by=model")).toEqual([
    { group: "first" },
    { group: "last" },
  ]);
  expect(fetch.mock.calls[1][0]).toContain("cursor=model%2Fnext");
});
