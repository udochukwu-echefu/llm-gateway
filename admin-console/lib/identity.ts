import "server-only";
import { z } from "zod";
import { adminRequest, redactCredentials } from "./admin-client";
const schema = z.object({
  key_id: z.string(),
  name: z.string(),
  role: z.enum(["platform", "org", "viewer"]),
  organization: z.object({ id: z.string(), name: z.string() }).nullable(),
});
export async function fetchIdentity(base: string, key: string) {
  const parsed = schema.parse(await adminRequest(base, key, "/me"));
  return {
    ...parsed,
    name: redactCredentials(parsed.name),
    organization: parsed.organization && {
      ...parsed.organization,
      name: redactCredentials(parsed.organization.name),
    },
  };
}
