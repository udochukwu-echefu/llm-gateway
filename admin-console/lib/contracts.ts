export interface Identity {
  key_id: string;
  name: string;
  role: "platform" | "org";
  organization: {
    id: string;
    name: string;
  } | null;
}
export interface NamedResource {
  id: string;
  name: string;
  created_at?: string;
}
export interface Page<T> {
  data: T[];
  next_cursor: string | number | null;
  total?: number;
}
export interface KeyRecord extends NamedResource {
  key_id: string;
  expires_at: string | null;
  revoked_at: string | null;
}
export type LimitName = "rpm" | "tpm" | "max_concurrency";
export interface Limits {
  overrides: Record<LimitName, number | null>;
  effective: Record<LimitName, number>;
}
export interface Budget {
  display_usd?: string | null;
  overrides: {
    usd: string | null;
    alert_at: string | null;
  };
  effective: {
    usd: string;
    alert_at: string;
  };
}
export interface Usage {
  group: string;
  requests: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  cost_usd: string | null;
  saved_usd: string | null;
  cache_hits: number;
  usage_missing: number;
  stream_incomplete: number;
}
export interface AuditEvent {
  id: number;
  occurred_at: string;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  details?: Record<string, unknown>;
}
