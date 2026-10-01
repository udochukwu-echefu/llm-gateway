import { z } from "zod";
const text = z
  .string()
  .min(1)
  .max(256)
  .refine((value) => !value.includes("lgwa_") && !value.includes("lgw_"));
const timestamp = z.iso.datetime({ offset: true });
const date = z.iso.date();
const page = {
  cursor: z.string().min(1).max(512).optional(),
  page_size: z.coerce.number().int().min(1).max(500).optional(),
};
export const requestQuery = z
  .object({
    ...page,
    page_size: z.coerce.number().int().min(1).max(200).optional(),
    since: timestamp.optional(),
    until: timestamp.optional(),
    team: text.optional(),
    key_id: z
      .string()
      .regex(/^[a-z2-7]{12}$/)
      .optional(),
    provider: z.enum(["groq", "deepseek", "gemini", "openai", "zai", "nvidia"]).optional(),
    model: text.optional(),
    alias: text.max(32).optional(),
    endpoint: z.enum(["chat", "embeddings"]).optional(),
    status: z
      .string()
      .regex(/^(?:[245]xx|[1-5][0-9]{2})$/)
      .optional(),
    outcome: z
      .enum([
        "success",
        "upstream_error",
        "client_disconnected",
        "stream_error",
        "gateway_error",
        "cache_hit",
      ])
      .optional(),
    cost_status: z
      .enum(["priced", "unpriced", "usage_missing", "stream_incomplete", "not_billed", "cached"])
      .optional(),
    stream: z.enum(["true", "false"]).optional(),
    cache_hit: z.enum(["true", "false"]).optional(),
    redacted: z.enum(["true", "false"]).optional(),
    fallback: z.enum(["true", "false"]).optional(),
    retried: z.enum(["true", "false"]).optional(),
    min_latency: z.coerce.number().finite().nonnegative().optional(),
  })
  .strict();
export const auditQuery = z
  .object({
    ...page,
    since: date.optional(),
    until: date.optional(),
    action: text.optional(),
    actor: text.optional(),
    target_type: z.enum(["organization", "team", "key", "admin-key"]).optional(),
  })
  .strict();
const keysQuery = z
  .object({
    ...page,
    team: text.optional(),
    q: text.max(128).optional(),
    status: z.enum(["active", "expiring", "expired", "revoked", "never-used"]).optional(),
  })
  .strict();
export function querySchema(path: string): z.ZodType {
  if (path === "/search") return z.object({ q: text.max(128) }).strict();
  if (path === "/audit") return auditQuery;
  if (/\/requests$/.test(path)) return requestQuery;
  if (/\/requests\//.test(path)) return z.object({}).strict();
  if (/\/analytics$/.test(path))
    return z
      .object({
        since: timestamp.optional(),
        until: timestamp.optional(),
        bucket: z.enum(["hour", "day"]).optional(),
        group_by: z.enum(["provider", "model", "team"]).optional(),
      })
      .strict();
  if (/\/keys$/.test(path)) return keysQuery;
  if (/\/usage$/.test(path))
    return z
      .object({
        ...page,
        since: date.optional(),
        until: date.optional(),
        group_by: z.enum(["team", "key", "model", "day"]).optional(),
      })
      .strict();
  if (/\/(model-policy|guardrails|residency|cache\/purge)$/.test(path))
    return z.object({ team: text.optional() }).strict();
  if (path === "/orgs" || /\/teams$/.test(path)) return z.object(page).strict();
  return z.object({}).strict();
}
export function validatedQuery(path: string, params: URLSearchParams): URLSearchParams | null {
  if (Array.from(params.keys()).length !== new Set(params.keys()).size) return null;
  const parsed = querySchema(path).safeParse(Object.fromEntries(params));
  if (!parsed.success) return null;
  return new URLSearchParams(
    Object.entries(parsed.data as Record<string, unknown>).map(([key, value]) => [
      key,
      String(value),
    ]),
  );
}
