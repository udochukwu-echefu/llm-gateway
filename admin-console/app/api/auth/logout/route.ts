import { NextResponse } from "next/server";
import { readConfig } from "@/lib/config";
import { hasSameOrigin } from "@/lib/origin";
import { readSession } from "@/lib/session";
export async function POST(request: Request) {
  if (!hasSameOrigin(request, readConfig().ADMIN_CONSOLE_ORIGIN))
    return NextResponse.json({ error: "Request origin is not allowed." }, { status: 403 });
  (await readSession()).destroy();
  return NextResponse.json({ signedOut: true }, { headers: { "Cache-Control": "no-store" } });
}
