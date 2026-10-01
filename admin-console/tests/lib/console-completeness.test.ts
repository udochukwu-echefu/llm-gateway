import { expect, test } from "vitest";
import { money } from "@/lib/money";
import { csvCell, csvRow } from "@/lib/csv";
import {
  readPreferences,
  savePreferences,
  defaultPreferences,
  PREFERENCES_KEY,
} from "@/lib/preferences";
import { absoluteTime, relativeTime } from "@/lib/relative-time";
import { updateQuery, listSort } from "@/lib/list-query";
import { validatedQuery } from "@/lib/bff-query";
import { scopedResults } from "@/lib/command-search";
import { budgetState } from "@/lib/budget-state";
import type { SearchResult } from "@/lib/console-contracts";

test("money rounds half up using exact integers and four small-value significant digits", () => {
  for (const [input, expected] of [
    ["1.005", "$1.01"],
    ["1.004999999999", "$1.00"],
    ["25.000000000001", "$25.00"],
    ["0.94885675", "$0.95"],
    ["0.28511", "$0.29"],
    ["0.00012345", "$0.0001235"],
    ["0.00012344", "$0.0001234"],
    ["0.0099995", "$0.01000"],
    ["0.000000000001", "$0.000000000001"],
    ["0", "$0.00"],
  ])
    expect(money(input)).toBe(expected);
});
test("CSV escapes delimiters quotes newlines and neutralises formula prefixes", () => {
  expect(csvCell('fake,"quoted"\nline')).toBe('"fake,""quoted""\nline"');
  for (const value of ["=FAKE_TEST()", "+FAKE", "-FAKE", "@FAKE", " \t=FAKE"])
    expect(csvCell(value)).toBe('"' + "'" + value + '"');
  expect(csvRow([null, "0.000000000001"])).toBe('"","0.000000000001"\r\n');
});
test("relative times include absolute zoned tooltip values and handle future dates", () => {
  const now = Date.parse("2026-10-01T12:00:00Z");
  expect(relativeTime("2026-10-01T11:55:00Z", now)).toBe("5 minutes ago");
  expect(relativeTime("2026-10-02T12:00:00Z", now)).toBe("tomorrow");
  expect(relativeTime("fake", now)).toBe("Unknown");
  expect(absoluteTime("2026-10-01T12:00:00Z", "utc")).toContain("UTC");
  expect(absoluteTime("2026-10-01T12:00:00Z", "local")).toContain(
    Intl.DateTimeFormat().resolvedOptions().timeZone,
  );
});
test("preferences persist in browser storage and malformed or injected preferences fall back", () => {
  localStorage.clear();
  expect(readPreferences(localStorage)).toEqual(defaultPreferences);
  const preferences = {
    ...defaultPreferences,
    theme: "dark" as const,
    density: "compact" as const,
    landing: "/requests" as const,
  };
  savePreferences(localStorage, preferences);
  expect(readPreferences(localStorage)).toEqual(preferences);
  localStorage.setItem(PREFERENCES_KEY, '{"theme":"fake","adminKey":"FAKE"}');
  expect(readPreferences(localStorage)).toEqual(defaultPreferences);
});
test("URL filter changes preserve unrelated state and removed chips disappear", () => {
  expect(
    updateQuery("org=Fake&status=5xx&sort=duration_ms", { status: null, team: "Fake team" }),
  ).toBe("org=Fake&sort=duration_ms&team=Fake+team");
  expect(
    listSort([{ cost_usd: "2.00" }, { cost_usd: "10.00" }], "cost_usd", "asc")[0].cost_usd,
  ).toBe("2.00");
});
test("new BFF query allowlists reject unknown duplicate and malformed filters", () => {
  for (const query of [
    "unknown=x",
    "stream=1",
    "page_size=201",
    "since=2026-01-01",
    "provider=fake",
    "status=6xx",
    "team=a&team=b",
    "min_latency=NaN",
  ])
    expect(validatedQuery("/orgs/Fake/requests", new URLSearchParams(query))).toBeNull();
  expect(
    validatedQuery("/orgs/Fake/requests", new URLSearchParams("status=5xx&fallback=true"))?.get(
      "status",
    ),
  ).toBe("5xx");
  expect(validatedQuery("/settings", new URLSearchParams("key=fake"))).toBeNull();
  expect(validatedQuery("/search", new URLSearchParams("q=Fake"))?.get("q")).toBe("Fake");
});
test("command palette keeps only the org admin workspace even if a response contains another org", () => {
  const results: SearchResult[] = [
    { kind: "org", id: "fake-a", name: "Fake A", org: "Fake A" },
    { kind: "key", id: "fake-b", name: "Fake B key", org: "Fake B" },
  ];
  expect(
    scopedResults(results, {
      key_id: "fake",
      name: "Fake admin",
      role: "org",
      organization: { id: "fake-a", name: "Fake A" },
    }),
  ).toEqual([results[0]]);
  expect(
    scopedResults(results, {
      key_id: "fake",
      name: "Fake admin",
      role: "platform",
      organization: null,
    }),
  ).toHaveLength(2);
});
test("budget state distinguishes threshold warnings and refusal from under-budget and unlimited", () => {
  expect(budgetState("0.2685", "0.25", "0.8")).toBe("over");
  expect(budgetState("0.2025", "0.25", "0.8")).toBe("warning");
  expect(budgetState("0.1", "0.25", "0.8")).toBe("under");
  expect(budgetState(null, "0.25", "0.8")).toBe("unknown");
  expect(budgetState("1", "0", "0.8")).toBe("unlimited");
});
