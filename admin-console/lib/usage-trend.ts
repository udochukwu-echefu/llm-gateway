import type { Usage } from "./contracts";

export function dailyTokens(row: Usage): number | null {
  if (row.prompt_tokens === null || row.completion_tokens === null
    || row.usage_missing > 0 || row.stream_incomplete > 0) return null;
  return row.prompt_tokens + row.completion_tokens;
}

export function trendSegments(values: (number | null)[]): string[] {
  const maximum = Math.max(1, ...values.filter((value) => value !== null));
  const segments: string[] = [];
  let points: string[] = [];
  for (const [index, value] of values.entries()) {
    if (value === null) {
      if (points.length) segments.push(points.join(" "));
      points = [];
    } else {
      points.push(trendPoint(index, value, values.length, maximum).join(","));
    }
  }
  if (points.length) segments.push(points.join(" "));
  return segments;
}

export function trendPoint(index: number, value: number, count: number, maximum: number) {
  return [60 + index * 470 / Math.max(1, count - 1), 140 - value * 105 / maximum];
}
