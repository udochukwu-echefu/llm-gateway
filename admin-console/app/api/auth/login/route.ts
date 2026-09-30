import { NextResponse } from "next/server";
import { z } from "zod";
import { readConfig } from "@/lib/config";
import { hasSameOrigin } from "@/lib/origin";
import { fetchIdentity } from "@/lib/identity";
import { readSession } from "@/lib/session";
import { AdminApiError } from "@/lib/admin-client";
import { loginThrottle } from "@/lib/login-throttle";
export async function POST(request: Request) {
  const config = readConfig();
  if (!hasSameOrigin(request, config.ADMIN_CONSOLE_ORIGIN))
    return NextResponse.json({ error: "Request origin is not allowed." }, { status: 403 });
  const client = request.headers.get("x-console-client-address") ?? "unknown";
  const retryAfter = loginThrottle.retryAfter(client);
  if (retryAfter) {
    return NextResponse.json(
      { error: "Too many sign-in attempts. Please try again in a minute." },
      {
        status: 429,
        headers: { "Retry-After": String(retryAfter), "Cache-Control": "no-store" },
      },
    );
  }
  const parsed = z
    .object({ key: z.string().regex(/^lgwa_[a-z2-7]{12}_[A-Za-z0-9_-]{43}$/) })
    .strict()
    .safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    loginThrottle.failed(client);
    return NextResponse.json({ error: "Enter a valid admin API key." }, { status: 400 });
  }
  try {
    const identity = await fetchIdentity(config.ADMIN_API_URL, parsed.data.key);
    (await readSession()).destroy();
    const session = await readSession();
    Object.assign(session, {
      adminKey: parsed.data.key,
      identity,
      issuedAt: Date.now(),
      lastSeen: Date.now(),
    });
    await session.save();
    loginThrottle.succeeded(client);
    return NextResponse.json({ identity }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (error instanceof AdminApiError && [401, 429].includes(error.status))
      loginThrottle.failed(client);
    return NextResponse.json(
      { error: error instanceof AdminApiError ? error.message : "Sign in failed." },
      { status: error instanceof AdminApiError ? error.status : 503 },
    );
  }
}
