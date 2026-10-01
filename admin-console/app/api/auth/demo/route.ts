import { NextResponse } from "next/server";
import { z } from "zod";
import { readConfig } from "@/lib/config";
import { hasSameOrigin } from "@/lib/origin";
import { fetchIdentity } from "@/lib/identity";
import { requireDemoViewer } from "@/lib/demo-role.mjs";
import { readSession } from "@/lib/session";
import { loginThrottle } from "@/lib/login-throttle";

export async function POST(request: Request) {
  const config = readConfig();
  if (!config.DEMO_MODE) return reply({ error: "Not found." }, 404);
  if (!hasSameOrigin(request, config.ADMIN_CONSOLE_ORIGIN))
    return reply({ error: "Request origin is not allowed." }, 403);
  const client = request.headers.get("x-console-client-address") ?? "unknown";
  const retryAfter = loginThrottle.retryAfter(client);
  if (retryAfter)
    return reply({ error: "Too many sign-in attempts. Please try again in a minute." }, 429, {
      "Retry-After": String(retryAfter),
    });
  // Public sign-ins count successes too: they need no credential to guess.
  loginThrottle.failed(client);
  const parsed = z
    .object({ as: z.enum(["platform", "org"]) })
    .strict()
    .safeParse(await request.json().catch(() => null));
  if (!parsed.success) return reply({ error: "Choose a demo scope." }, 400);
  const key = parsed.data.as === "platform" ? config.DEMO_VIEWER_KEY : config.DEMO_ORG_VIEWER_KEY;
  if (!key) return reply({ error: "Not found." }, 404);
  try {
    const identity = await fetchIdentity(config.ADMIN_API_URL, key);
    requireDemoViewer(identity, parsed.data.as);
    (await readSession()).destroy();
    const session = await readSession();
    Object.assign(session, {
      adminKey: key,
      identity,
      demo: true,
      issuedAt: Date.now(),
      lastSeen: Date.now(),
    });
    await session.save();
    return reply({ identity }, 200);
  } catch {
    return reply({ error: "The demo is unavailable. Please try again later." }, 503);
  }
}
function reply(body: unknown, status: number, headers: Record<string, string> = {}) {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "no-store", ...headers } });
}
