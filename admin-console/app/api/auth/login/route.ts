import { NextResponse } from "next/server";
import { z } from "zod";
import { readConfig } from "@/lib/config";
import { hasSameOrigin } from "@/lib/origin";
import { fetchIdentity } from "@/lib/identity";
import { readSession } from "@/lib/session";
import { AdminApiError } from "@/lib/admin-client";
export async function POST(request: Request) {
  const config = readConfig();
  if (!hasSameOrigin(request, config.ADMIN_CONSOLE_ORIGIN))
    return NextResponse.json({ error: "Request origin is not allowed." }, { status: 403 });
  const parsed = z.object({ key: z.string().regex(/^lgwa_[a-z2-7]{12}_[A-Za-z0-9_-]{43}$/) }).strict().safeParse(await request.json().catch(() => null));
  if (!parsed.success)
    return NextResponse.json({ error: "Enter a valid admin API key." }, { status: 400 });
  try {
    const identity = await fetchIdentity(config.ADMIN_API_URL, parsed.data.key);
    (await readSession()).destroy();
    const session = await readSession();
    Object.assign(session, { adminKey: parsed.data.key, identity, issuedAt: Date.now(), lastSeen: Date.now() });
    await session.save();
    return NextResponse.json({ identity }, { headers: { "Cache-Control": "no-store" } });
  }
  catch (error) {
    return NextResponse.json({ error: error instanceof AdminApiError ? error.message : "Sign in failed." }, { status: error instanceof AdminApiError ? error.status : 503 });
  }
}
