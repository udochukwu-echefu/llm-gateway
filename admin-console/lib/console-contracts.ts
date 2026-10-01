import type { KeyRecord } from "./contracts";
export interface RequestAttempt {
  id: string;
  request_id: string;
  created_at: string;
  team_id: string;
  key_id: string;
  provider: string;
  model: string;
  endpoint: string;
  stream: boolean;
  status_code: number;
  outcome: string;
  cost_status: string;
  cost_usd: string | null;
  saved_usd: string | null;
  duration_ms: number | null;
  ttfb_ms: number | null;
  attempt: number;
  fallback_from: string | null;
  alias: string | null;
  redaction_count: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
}
export interface AnalyticsRow {
  bucket: string;
  group?: string;
  requests: number;
  error_rate: number | string;
  duration_p50: number | null;
  duration_p95: number | null;
  duration_p99: number | null;
  ttfb_p50: number | null;
  ttfb_p95: number | null;
  ttfb_p99: number | null;
  fallback_count: number;
  retry_count: number;
  cache_hit_rate: number | string;
  saved_usd: string | null;
  redaction_count: number | null;
}
export interface ConsoleKey extends KeyRecord {
  team_id: string;
  last_used_at: string | null;
}
export interface SearchResult {
  kind: "org" | "team" | "key";
  name: string;
  id: string;
  org: string;
  team?: string;
}
export interface Price {
  effective_from: string;
  unpriced: boolean;
  input_price: string | null;
  output_price: string | null;
  cached_input_price: string | null;
  source_url: string;
  checked_on: string;
}
export interface ConsoleModel {
  name: string;
  provider: string;
  maker: string;
  region: string;
  endpoints: string[];
  prices: Price[];
  effective_price: Price | null;
  region_source_url: string | null;
  region_checked_on: string | null;
}
