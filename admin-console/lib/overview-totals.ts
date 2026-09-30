import type { KeyRecord, Usage } from "./contracts";
import { pico } from "./money";
export function decimalPico(amount: bigint): string {
  return `${amount / 10n ** 12n}.${(amount % 10n ** 12n).toString().padStart(12, "0")}`;
}
export function sumDecimal(values: (string | null)[]): string | null {
  const known = values.filter((v) => v !== null);
  return known.length ? decimalPico(known.reduce((sum, v) => sum + pico(v), 0n)) : null;
}
export function summarize(rows: Usage[], keys: KeyRecord[], teams: number, now = Date.now()) {
  const add = (value: (row: Usage) => number) => rows.reduce((n, row) => n + value(row), 0);
  return {
    spend: rows.length ? sumDecimal(rows.map((r) => r.cost_usd)) : "0",
    unpriced: add((r) => r.usage_missing + r.stream_incomplete),
    requests: add((r) => r.requests),
    tokens: add((r) => (r.prompt_tokens ?? 0) + (r.completion_tokens ?? 0)),
    incompleteTokens: rows.some(
      (r) =>
        r.prompt_tokens === null ||
        r.completion_tokens === null ||
        r.usage_missing + r.stream_incomplete > 0,
    ),
    savings: rows.some((r) => r.cache_hits > 0)
      ? sumDecimal(rows.filter((r) => r.cache_hits > 0).map((r) => r.saved_usd))
      : "0",
    unknownSavings: rows.some((r) => r.cache_hits > 0 && r.saved_usd === null),
    activeKeys: keys.filter(
      (key) => !key.revoked_at && (!key.expires_at || Date.parse(key.expires_at) > now),
    ).length,
    teams,
  };
}
export function combineGroups(rows: Usage[]): Usage[] {
  const groups = new Map<string, Usage>();
  for (const row of rows) {
    const prior = groups.get(row.group);
    if (!prior) {
      groups.set(row.group, { ...row });
      continue;
    }
    groups.set(row.group, {
      group: row.group,
      requests: prior.requests + row.requests,
      prompt_tokens:
        prior.prompt_tokens === null && row.prompt_tokens === null
          ? null
          : (prior.prompt_tokens ?? 0) + (row.prompt_tokens ?? 0),
      completion_tokens:
        prior.completion_tokens === null && row.completion_tokens === null
          ? null
          : (prior.completion_tokens ?? 0) + (row.completion_tokens ?? 0),
      cost_usd: sumDecimal([prior.cost_usd, row.cost_usd]),
      saved_usd: sumDecimal([prior.saved_usd, row.saved_usd]),
      cache_hits: prior.cache_hits + row.cache_hits,
      usage_missing: prior.usage_missing + row.usage_missing,
      stream_incomplete: prior.stream_incomplete + row.stream_incomplete,
    });
  }
  return [...groups.values()].sort((a, b) => a.group.localeCompare(b.group));
}
