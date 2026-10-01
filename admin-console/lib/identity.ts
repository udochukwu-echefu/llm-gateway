import "server-only";
import { z } from "zod";
import { adminRequest, redactCredentials } from "./admin-client";
const schema = z.object({
  key_id: z.string(),
  name: z.string(),
  role: z.enum(["platform", "org", "viewer"]),
  organization: z.object({ id: z.string(), name: z.string() }).nullable(),
});
export async function fetchIdentity(base: string, key: string, demo = false) {
  const parsed = schema.parse(await adminRequest(base, key, "/me"));
  return {
    ...parsed,
    name:
      demo && parsed.role === "viewer"
        ? `Demo visitor · ${parsed.organization ? redactCredentials(parsed.organization.name) : "Platform"} viewer`
        : redactCredentials(parsed.name),
    organization: parsed.organization && {
      ...parsed.organization,
      name: redactCredentials(parsed.organization.name),
    },
  };
}
