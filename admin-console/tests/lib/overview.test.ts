import { expect, test, vi } from "vitest";
import { combineGroups, summarize, sumDecimal } from "@/lib/overview-totals";
import type { Usage, KeyRecord } from "@/lib/contracts";
const row: Usage = {
  group: "Search",
  requests: 2,
  prompt_tokens: 120,
  completion_tokens: 40,
  cost_usd: "0.000000000001",
  saved_usd: "1.25",
  cache_hits: 1,
  usage_missing: 0,
  stream_incomplete: 0,
};
test("overview totals use exact decimals and retain unknown usage and savings", () => {
  const missing = {
    ...row,
    cost_usd: null,
    saved_usd: null,
    prompt_tokens: null,
    completion_tokens: null,
    usage_missing: 2,
  };
  const keys = [
    { id: "a", name: "Fake", key_id: "fakepublicid", expires_at: null, revoked_at: null },
    { id: "b", name: "Fake", key_id: "fakepublicid", expires_at: null, revoked_at: "2026-01-01" },
    { id: "c", name: "Fake", key_id: "fakepublicid", expires_at: "2026-01-01", revoked_at: null },
  ] satisfies KeyRecord[];
  expect(summarize([row, missing], keys, 3, Date.parse("2026-09-30"))).toEqual({
    spend: "0.000000000001",
    unpriced: 2,
    requests: 4,
    tokens: 160,
    incompleteTokens: true,
    savings: "1.250000000000",
    unknownSavings: true,
    activeKeys: 1,
    teams: 3,
  });
  expect(summarize([missing], [], 0).spend).toBeNull();
  expect(summarize([], [], 0).spend).toBe("0");
  expect(sumDecimal(["0.1", "0.2"])).toBe("0.300000000000");
});
test("overview combines model and day groups across organisations", () => {
  const combined = combineGroups([row, { ...row, cost_usd: "2.01" }]);
  expect(combined).toHaveLength(1);
  expect(combined[0].requests).toBe(4);
  expect(combined[0].cost_usd).toBe("2.010000000001");
});
vi.mock("@/lib/browser-api", () => ({ browserApi: vi.fn() }));
test("overview drains all org and audit pages and shows the five latest events", async () => {
  const { browserApi } = await import("@/lib/browser-api");
  vi.mocked(browserApi).mockImplementation(async (path) => {
    if (path.startsWith("/api/admin/orgs")) return { data: [], next_cursor: null } as never;
    if (path.includes("cursor=5"))
      return { data: [{ id: 6 }, { id: 7 }], next_cursor: null } as never;
    return { data: [1, 2, 3, 4, 5].map((id) => ({ id })), next_cursor: 5 } as never;
  });
  const { loadOverview } = await import("@/lib/overview-data");
  const data = await loadOverview();
  expect(data.recent.map((e) => e.id)).toEqual([7, 6, 5, 4, 3]);
});
