import { z } from "zod";
const name = z.string().trim().min(1).max(256).refine((v) => !/lgwa_|lgw_/.test(v), "Names cannot contain credentials.");
export const nameSchema = z.object({ name }).strict();
export const keySchema = nameSchema.extend({ expires_in_days: z.number().int().positive().max(36500).nullable().optional() });
export const limitsSchema = z.object({ rpm: z.number().int().nonnegative().nullable(), tpm: z.number().int().nonnegative().nullable(), max_concurrency: z.number().int().nonnegative().nullable() }).strict();
export const moneySchema = z.string().regex(/^\d{1,7}(?:\.\d{1,12})?$/).pipe(z.string().refine((value) => BigInt(value.split(".")[0]) < 9223372n || (value.split(".")[0] === "9223372" && (value.split(".")[1] ?? "").padEnd(12, "0") <= "036854775807")));
export const thresholdSchema = z.string().regex(/^(?:0\.\d{1,12}|1(?:\.0{1,12})?)$/).refine((v) => /[1-9]/.test(v));
export const budgetSchema = z.object({ usd: moneySchema, alert_at: thresholdSchema }).strict();
const segment = "[^/]+";
export function operationSchema(method: string, path: string): z.ZodType | null | undefined {
  if (method === "GET" && (path === "/orgs" || path === "/audit" || path === "/audit/verify" || new RegExp(`^/orgs/${segment}/(teams|keys|usage)$`).test(path) || new RegExp(`^/orgs/${segment}/teams/${segment}/(limits|budget)$`).test(path)))
    return null;
  if (method === "POST" && (path === "/orgs" || new RegExp(`^/orgs/${segment}/teams$`).test(path)))
    return nameSchema;
  if (method === "POST" && new RegExp(`^/orgs/${segment}/teams/${segment}/keys$`).test(path))
    return keySchema;
  if (method === "POST" && /^\/keys\/[a-z2-7]{12}\/revoke$/.test(path))
    return null;
  if (method === "PUT" && new RegExp(`^/orgs/${segment}/teams/${segment}/limits$`).test(path))
    return limitsSchema;
  if (method === "PUT" && new RegExp(`^/orgs/${segment}/teams/${segment}/budget$`).test(path))
    return budgetSchema;
  if (method === "DELETE" && new RegExp(`^/orgs/${segment}/teams/${segment}/limits$`).test(path))
    return null;
  return undefined;
}
export function isCreation(method: string, path: string) { return method === "POST" && !path.endsWith("/revoke"); }
