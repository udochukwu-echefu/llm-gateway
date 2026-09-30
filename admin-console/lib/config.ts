import "server-only";
import { z } from "zod";
const httpUrl = z.url().refine((value) => {
  const url = new URL(value);
  return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password && !url.search && !url.hash && url.pathname === "/";
});
const schema = z.object({
  ADMIN_API_URL: httpUrl,
  ADMIN_CONSOLE_ORIGIN: httpUrl,
  ADMIN_CONSOLE_SESSION_SECRET: z.string().min(32).refine((value) => Buffer.byteLength(value) >= 32),
});
export function readConfig(env: Record<string, string | undefined> = process.env) {
  const parsed = schema.safeParse(env);
  if (!parsed.success)
    throw new Error("Invalid console configuration: check ADMIN_API_URL, ADMIN_CONSOLE_ORIGIN and a session secret of at least 32 bytes.");
  return parsed.data;
}
