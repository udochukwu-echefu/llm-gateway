import { NextResponse, type NextRequest } from "next/server";
import { readConfig } from "@/lib/config";
import { hasSameOrigin } from "@/lib/origin";
import { readSession } from "@/lib/session";
import { isActive } from "@/lib/session-policy";
import { AdminApiError, adminRequest } from "@/lib/admin-client";
import { isCreation, operationSchema } from "@/lib/bff-policy";
import { policyHeaders, residencySchema, residencySchemaFor } from "@/lib/policy-schemas";
import type { Catalog } from "@/lib/policy-contracts";
import { browserResponse } from "@/lib/bff-response";
import { validatedQuery } from "@/lib/bff-query";
type Context = {
  params: Promise<{
    path: string[];
  }>;
};
async function forward(request: NextRequest, context: Context) {
  const config = readConfig();
  if (rejectsOrigin(request, config.ADMIN_CONSOLE_ORIGIN))
    return reply({ error: "Request origin is not allowed." }, 403);
  const segments = await parseSegments(context);
  if (segments instanceof NextResponse) return segments;
  const path = "/" + segments.map(encodeURIComponent).join("/");
  const schema = operationSchema(request.method, path);
  if (schema === undefined) return reply({ error: "Not found." }, 404);
  const session = await readSession();
  if (!isActive(session)) {
    session.destroy();
    return reply({ error: "Please sign in again." }, 401);
  }
  let body: unknown;
  if (schema) {
    const input: unknown = await request.json().catch(() => null);
    if (schema === residencySchema) body = input;
    else {
      const parsed = schema.safeParse(input);
      if (!parsed.success) return reply({ error: "Check the form values and try again." }, 400);
      body = parsed.data;
    }
  }
  const conditional = policyHeaders(request.method, path, request.headers.get("if-match"));
  if (conditional === null)
    return reply({ error: "A valid policy version is required. Reload the policy." }, 400);
  const idempotency = request.headers.get("idempotency-key");
  if (isCreation(request.method, path) && (!idempotency || !/^[0-9a-f-]{36}$/.test(idempotency)))
    return reply({ error: "A submission ID is required." }, 400);
  const query = validatedQuery(path, request.nextUrl.searchParams);
  if (!query) return reply({ error: "Invalid query." }, 400);
  return forwardAuthenticated(
    request,
    config,
    session,
    path,
    query,
    body,
    idempotency,
    conditional,
  );
}
async function forwardAuthenticated(
  request: NextRequest,
  config: ReturnType<typeof readConfig>,
  session: Awaited<ReturnType<typeof readSession>>,
  path: string,
  query: URLSearchParams,
  body: unknown,
  idempotency: string | null,
  conditional: Record<string, string>,
) {
  try {
    if (request.method === "PUT" && path.endsWith("/residency")) {
      const catalog = await adminRequest<Catalog>(
        config.ADMIN_API_URL,
        session.adminKey!,
        "/catalog",
      );
      const parsed = residencySchemaFor(catalog).safeParse(body);
      if (!parsed.success) return reply({ error: "Check the form values and try again." }, 400);
      body = parsed.data;
    }
    const target = path + (query.size ? `?${query}` : "");
    const result = await adminRequest(config.ADMIN_API_URL, session.adminKey!, target, {
      method: request.method,
      headers: {
        ...(idempotency && isCreation(request.method, path)
          ? { "Idempotency-Key": idempotency }
          : {}),
        ...conditional,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    session.lastSeen = Date.now();
    await session.save();
    return reply(browserResponse(result, request.method === "POST" && path.endsWith("/keys")), 200);
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) session.destroy();
    const message =
      error instanceof AdminApiError ? error.message : "The request could not be completed.";
    return reply({ error: message }, error instanceof AdminApiError ? error.status : 500);
  }
}

async function parseSegments(context: Context): Promise<string[] | NextResponse> {
  let segments: string[];
  try {
    segments = (await context.params).path.map(decodeURIComponent);
  } catch {
    return reply({ error: "Not found." }, 404);
  }
  if (segments.some((s) => !s || s === "." || s === ".." || /[/]/.test(s)))
    return reply({ error: "Not found." }, 404);
  return segments;
}

function rejectsOrigin(request: NextRequest, expected: string) {
  return request.method !== "GET" && !hasSameOrigin(request, expected);
}

function reply(body: unknown, status: number) {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "no-store" } });
}
export { forward as GET, forward as POST, forward as PUT, forward as DELETE };
