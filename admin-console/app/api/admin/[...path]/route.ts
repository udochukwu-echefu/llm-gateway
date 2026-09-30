import { NextResponse, type NextRequest } from "next/server";
import { readConfig } from "@/lib/config";
import { hasSameOrigin } from "@/lib/origin";
import { readSession } from "@/lib/session";
import { isActive } from "@/lib/session-policy";
import { AdminApiError, adminRequest } from "@/lib/admin-client";
import { isCreation, operationSchema } from "@/lib/bff-policy";
import { browserResponse } from "@/lib/bff-response";
type Context = {
  params: Promise<{
    path: string[];
  }>;
};
async function forward(request: NextRequest, context: Context) {
  const config = readConfig();
  if (request.method !== "GET" && !hasSameOrigin(request, config.ADMIN_CONSOLE_ORIGIN))
    return reply({ error: "Request origin is not allowed." }, 403);
  let segments: string[];
  try {
    segments = (await context.params).path.map(decodeURIComponent);
  }
  catch {
    return reply({ error: "Not found." }, 404);
  }
  if (segments.some((s) => !s || s === "." || s === ".." || /[/\\?#%]/.test(s)))
    return reply({ error: "Not found." }, 404);
  const path = "/" + segments.map(encodeURIComponent).join("/");
  const schema = operationSchema(request.method, path);
  if (schema === undefined)
    return reply({ error: "Not found." }, 404);
  const session = await readSession();
  if (!isActive(session)) {
    session.destroy();
    return reply({ error: "Please sign in again." }, 401);
  }
  let body: unknown;
  if (schema) {
    const parsed = schema.safeParse(await request.json().catch(() => null));
    if (!parsed.success)
      return reply({ error: "Check the form values and try again." }, 400);
    body = parsed.data;
  }
  const idempotency = request.headers.get("idempotency-key");
  if (isCreation(request.method, path) && (!idempotency || !/^[0-9a-f-]{36}$/.test(idempotency)))
    return reply({ error: "A submission ID is required." }, 400);
  const query = new URLSearchParams();
  for (const [key, value] of request.nextUrl.searchParams) {
    if (!["cursor", "page_size", "team", "since", "until", "group_by", "action"].includes(key))
      return reply({ error: "Invalid query." }, 400);
    query.append(key, value);
  }
  try {
    const result = await adminRequest(config.ADMIN_API_URL, session.adminKey!, path + (query.size ? `?${query}` : ""), {
      method: request.method, headers: idempotency ? { "Idempotency-Key": idempotency } : {}, body: body === undefined ? undefined : JSON.stringify(body),
    });
    session.lastSeen = Date.now();
    await session.save();
    return reply(browserResponse(result, request.method === "POST" && path.endsWith("/keys")), 200);
  }
  catch (error) {
    if (error instanceof AdminApiError && error.status === 401)
      session.destroy();
    return reply({ error: error instanceof AdminApiError ? error.message : "The request could not be completed." }, error instanceof AdminApiError ? error.status : 500);
  }
}
function reply(body: unknown, status: number) { return NextResponse.json(body, { status, headers: { "Cache-Control": "no-store" } }); }
export { forward as GET, forward as POST, forward as PUT, forward as DELETE };
