import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import type { Usage } from "@/lib/contracts";
import { DailyUsage } from "@/components/daily-usage";
import { dailyTokens, trendSegments } from "@/lib/usage-trend";

const known: Usage = {
  group: "2026-09-01",
  requests: 3,
  prompt_tokens: 20,
  completion_tokens: 10,
  cost_usd: "0.01",
  saved_usd: null,
  cache_hits: 0,
  usage_missing: 0,
  stream_incomplete: 0,
};

test("unknown token totals make chart gaps and remain explicit in the text alternative", () => {
  const unknown = { ...known, group: "2026-09-02", prompt_tokens: null, usage_missing: 1 };
  const rows = [known, unknown, { ...known, group: "2026-09-03" }];
  expect(rows.map(dailyTokens)).toEqual([30, null, 30]);
  expect(trendSegments(rows.map(dailyTokens))).toHaveLength(2);
  expect(dailyTokens({ ...known, stream_incomplete: 1 })).toBeNull();
  render(<DailyUsage rows={rows} />);
  expect(screen.getByRole("img", { name: "Daily requests" })).toBeDefined();
  const tokens = screen.getByRole("img", { name: "Daily total tokens" });
  expect(tokens.querySelectorAll("rect.chart-point")).toHaveLength(2);
  expect(screen.getByText(/Legend:/)).toBeDefined();
  expect(screen.getByText(/text alternative to both charts/)).toBeDefined();
  expect(screen.getAllByText("Unknown")).toHaveLength(2);
});
