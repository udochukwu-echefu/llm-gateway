import { z } from "zod";

const identitySchema = z.object({
  role: z.literal("viewer"),
  organization: z.object({ id: z.string().min(1), name: z.string() }).nullable(),
});

/** @param {unknown} identity @param {"platform" | "org"} scope */
export function requireDemoViewer(identity, scope) {
  const parsed = identitySchema.safeParse(identity);
  if (
    !parsed.success ||
    (scope === "platform"
      ? parsed.data.organization !== null
      : parsed.data.organization === null || parsed.data.organization.name !== "Northwind Health")
  ) {
    throw new Error("Demo sign-in requires a viewer key with the configured scope.");
  }
}

/** @param {ReturnType<typeof import('./config-schema.mjs').readConfig>} config */
export async function checkDemoKeys(config) {
  if (!config.DEMO_MODE) return;
  for (const [scope, key] of /** @type {const} */ ([
    ["platform", config.DEMO_VIEWER_KEY],
    ["org", config.DEMO_ORG_VIEWER_KEY],
  ])) {
    if (!key) continue;
    try {
      const response = await fetch(`${config.ADMIN_API_URL}/admin/v1/me`, {
        headers: { Authorization: `Bearer ${key}` },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok) throw new Error("Demo identity unavailable.");
      requireDemoViewer(await response.json(), scope);
    } catch {
      // Never include upstream bodies, credentials or network exception details.
      throw new Error(
        `Demo startup refused: ${scope} key must be a valid scoped viewer; check the private gateway.`,
      );
    }
  }
}
