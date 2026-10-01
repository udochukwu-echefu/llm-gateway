import { z } from "zod";

const httpUrl = z.url().refine((value) => {
  const url = new URL(value);
  return (
    ["http:", "https:"].includes(url.protocol) &&
    !url.username &&
    !url.password &&
    !url.search &&
    !url.hash &&
    url.pathname === "/"
  );
});

const booleanSetting = z.enum(["true", "false"]).transform((value) => value === "true");
const demoKey = z.string().regex(/^lgwa_[a-z2-7]{12}_[A-Za-z0-9_-]{43}$/);
export const configSchema = z
  .object({
    ADMIN_API_URL: httpUrl,
    ADMIN_CONSOLE_ORIGIN: httpUrl,
    ADMIN_CONSOLE_SESSION_SECRET: z
      .string()
      .min(32)
      .refine((value) => Buffer.byteLength(value) >= 32),
    ADMIN_CONSOLE_TRUSTED_PROXY_HOPS: z.coerce.number().int().min(0).max(32).default(0),
    DEMO_MODE: booleanSetting.default(false),
    DEMO_VIEWER_KEY: demoKey.optional(),
    DEMO_ORG_VIEWER_KEY: demoKey.optional(),
    DEMO_ALLOW_KEY_SIGN_IN: booleanSetting.default(false),
  })
  .refine((config) => !config.DEMO_MODE || !!config.DEMO_VIEWER_KEY);

/** @param {Record<string, string | undefined>} env */
export function readConfig(env = process.env) {
  const parsed = configSchema.safeParse(env);
  if (!parsed.success) {
    throw new Error(
      "Invalid console configuration: check ADMIN_API_URL, ADMIN_CONSOLE_ORIGIN, " +
        "a session secret of at least 32 bytes, trusted proxy hops (0–32), " +
        "demo booleans (true/false) and configured demo viewer keys.",
    );
  }
  return parsed.data;
}
