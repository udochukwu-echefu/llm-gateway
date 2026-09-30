import { z } from "zod";
import { actions, detectors, type Catalog } from "./policy-contracts";
import { catalogRegions } from "./policy-regions";
export const ifMatchSchema = z.string().regex(/^"[0-9a-f]{64}"$/);
const pattern = z
  .string()
  .max(256)
  .regex(
    /^(groq|openai|gemini|deepseek)\/(\*|[A-Za-z0-9][A-Za-z0-9._-]*(\/[A-Za-z0-9][A-Za-z0-9._-]*)*)$/,
  );
const unique = (values: string[]) => [...new Set(values)];
export const modelPolicySchema = z
  .object({ allow: z.array(pattern).max(256).transform(unique) })
  .strict();
const detector = z.enum(detectors);
const action = z.enum(actions);
const pair = z
  .string()
  .max(64)
  .refine((value) => {
    const parts = value.split("=");
    return (
      parts.length === 2 &&
      detector.safeParse(parts[0]).success &&
      action.safeParse(parts[1]).success
    );
  });
export const guardrailsSchema = z
  .object({
    actions: z
      .array(pair)
      .max(7)
      .refine(
        (values) => new Set(values.map((value) => value.split("=")[0])).size === values.length,
        "Choose one action per detector",
      ),
  })
  .strict();
export function residencySchemaFor(catalog?: Catalog) {
  const regions = catalogRegions(catalog);
  return z
    .object({ regions: z.array(z.enum(regions)).max(regions.length).transform(unique) })
    .strict();
}
export const residencySchema = residencySchemaFor();
export function isPolicyPath(path: string) {
  return /^\/orgs\/[^/]+\/(model-policy|guardrails|residency)$/.test(path);
}
export function policyHeaders(
  method: string,
  path: string,
  supplied: string | null,
): Record<string, string> | null {
  if (!isPolicyPath(path) || method === "GET") return {};
  const checked = ifMatchSchema.safeParse(supplied);
  return checked.success ? { "If-Match": checked.data } : null;
}
