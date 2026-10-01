import { NextRequest, NextResponse } from "next/server";
import { readSession } from "@/lib/session";
import { isActive } from "@/lib/session-policy";
import { readConfig } from "@/lib/config";
import { validatedQuery } from "@/lib/bff-query";
import { adminRequest, AdminApiError } from "@/lib/admin-client";
import { csvStream, requestColumns, auditColumns } from "@/lib/csv-stream";
import type { Page } from "@/lib/contracts";
export async function GET(request: NextRequest, context: { params: Promise<{ kind: string }> }) {
  const { kind } = await context.params;
  if (!["requests", "audit"].includes(kind))
    return NextResponse.json({ error: "Not found." }, { status: 404 });
  const params = new URLSearchParams(request.nextUrl.searchParams);
  if (Array.from(params.keys()).length !== new Set(params.keys()).size)
    return NextResponse.json({ error: "Duplicate query." }, { status: 400 });
  const org = params.get("org");
  params.delete("org");
  if (kind === "requests" && (!org || org.length > 256 || /[/]|lgwa_|lgw_/.test(org)))
    return NextResponse.json({ error: "Invalid organisation." }, { status: 400 });
  if (kind === "audit" && org)
    return NextResponse.json({ error: "Invalid query." }, { status: 400 });
  const path = kind === "requests" ? `/orgs/${encodeURIComponent(org!)}/requests` : "/audit";
  const query = validatedQuery(path, params);
  if (!query) return NextResponse.json({ error: "Invalid query." }, { status: 400 });
  query.delete("cursor");
  query.set("page_size", kind === "requests" ? "200" : "500");
  const session = await readSession();
  if (!isActive(session)) {
    session.destroy();
    return NextResponse.json({ error: "Please sign in again." }, { status: 401 });
  }
  const config = readConfig();
  try {
    const first = await adminRequest<Page<Record<string, unknown>>>(
      config.ADMIN_API_URL,
      session.adminKey!,
      `${path}?${query}`,
    );
    session.lastSeen = Date.now();
    await session.save();
    return new Response(
      csvStream(
        first,
        kind === "requests" ? requestColumns : auditColumns,
        config.ADMIN_API_URL,
        session.adminKey!,
        path,
        query,
      ),
      {
        headers: {
          "Content-Type": "text/csv; charset=utf-8",
          "Content-Disposition": `attachment; filename="${kind}.csv"`,
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
        },
      },
    );
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) session.destroy();
    return NextResponse.json(
      { error: error instanceof AdminApiError ? error.message : "Export failed." },
      { status: error instanceof AdminApiError ? error.status : 500 },
    );
  }
}
