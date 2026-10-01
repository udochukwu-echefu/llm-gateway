import { z } from "zod";
import { modelPolicySchema, guardrailsSchema, residencySchema } from "./policy-schemas";
const name = z
  .string()
  .trim()
  .min(1)
  .max(256)
  .refine(
    (value) => !value.includes("/") && value !== "." && value !== "..",
    "Names cannot contain / or be . or ..",
  )
  .refine((value) => !/lgwa_|lgw_/.test(value), "Names cannot contain credentials.");
export const nameSchema = z.object({ name }).strict();
export const keySchema = nameSchema.extend({
  expires_in_days: z.number().int().positive().max(36500).nullable().optional(),
});
export const limitsSchema = z
  .object({
    rpm: z.number().int().nonnegative().nullable(),
    tpm: z.number().int().nonnegative().nullable(),
    max_concurrency: z.number().int().nonnegative().nullable(),
  })
  .strict();
export const moneySchema = z
  .string()
  .regex(/^\d{1,7}(?:\.\d{1,12})?$/)
  .pipe(z.string().refine(isWithinMoneyLimit));

function isWithinMoneyLimit(value: string) {
  const [whole, fraction = ""] = value.split(".");
  return (
    BigInt(whole) < 9223372n || (whole === "9223372" && fraction.padEnd(12, "0") <= "036854775807")
  );
}

export const thresholdSchema = z
  .string()
  .regex(/^(?:0\.\d{1,12}|1(?:\.0{1,12})?)$/)
  .refine((value) => /[1-9]/.test(value));
export const budgetSchema = z.object({ usd: moneySchema, alert_at: thresholdSchema }).strict();
const segment = "[^/]+";
const teamPath = `/orgs/${segment}/teams/${segment}`;
const routes: { method: string; path: RegExp; schema: z.ZodType | null }[] = [
  {
    method: "GET",
    path: /^\/(orgs|catalog|settings|providers|search|audit|audit\/verify)$/,
    schema: null,
  },
  {
    method: "GET",
    path: new RegExp(`^/orgs/${segment}/(teams|keys|usage|requests|analytics)$`),
    schema: null,
  },
  { method: "GET", path: new RegExp(`^${teamPath}/(limits|budget)$`), schema: null },
  { method: "GET", path: new RegExp(`^/orgs/${segment}/requests/${segment}$`), schema: null },
  ...["model-policy", "guardrails", "residency"].flatMap((kind) => [
    { method: "GET", path: new RegExp(`^/orgs/${segment}/${kind}$`), schema: null },
    { method: "DELETE", path: new RegExp(`^/orgs/${segment}/${kind}$`), schema: null },
    {
      method: "PUT",
      path: new RegExp(`^/orgs/${segment}/${kind}$`),
      schema:
        kind === "model-policy"
          ? modelPolicySchema
          : kind === "guardrails"
            ? guardrailsSchema
            : residencySchema,
    },
  ]),
  { method: "POST", path: new RegExp(`^/orgs/${segment}/cache/purge$`), schema: null },
  { method: "POST", path: /^\/orgs$/, schema: nameSchema },
  { method: "POST", path: new RegExp(`^/orgs/${segment}/teams$`), schema: nameSchema },
  { method: "POST", path: new RegExp(`^${teamPath}/keys$`), schema: keySchema },
  { method: "POST", path: /^\/keys\/[a-z2-7]{12}\/revoke$/, schema: null },
  { method: "PUT", path: new RegExp(`^${teamPath}/limits$`), schema: limitsSchema },
  { method: "PUT", path: new RegExp(`^${teamPath}/budget$`), schema: budgetSchema },
  { method: "DELETE", path: new RegExp(`^${teamPath}/limits$`), schema: null },
];

export function operationSchema(method: string, path: string): z.ZodType | null | undefined {
  return routes.find((route) => route.method === method && route.path.test(path))?.schema;
}
export function isCreation(method: string, path: string) {
  return method === "POST" && (path === "/orgs" || /\/teams(?:\/[^/]+\/keys)?$/.test(path));
}
