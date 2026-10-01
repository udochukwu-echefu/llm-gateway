import { NextRequest, NextResponse } from "next/server";
import { getIronSession, nextProxyCookies } from "iron-session";
import { readConfig } from "./lib/config";
import { fetchIdentity } from "./lib/identity";
import { AdminApiError } from "./lib/admin-client";
import { isActive, sessionOptions, type SessionData } from "./lib/session-policy";
export async function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const policy = createCsp(nonce);
  const headers = new Headers(request.headers);
  headers.delete("x-console-identity");
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", policy);
  let response = NextResponse.next({ request: { headers } });
  if (!request.nextUrl.pathname.startsWith("/api/") && request.nextUrl.pathname !== "/login") {
    const config = readConfig();
    const session = await proxySession(request, response, config.ADMIN_CONSOLE_SESSION_SECRET);
    if (!isActive(session)) {
      response = NextResponse.redirect(new URL("/login", request.url));
      (await proxySession(request, response, config.ADMIN_CONSOLE_SESSION_SECRET)).destroy();
    } else {
      try {
        const identity = await fetchIdentity(
          config.ADMIN_API_URL,
          session.adminKey!,
          config.DEMO_MODE,
        );
        headers.set("x-console-identity", JSON.stringify(identity));
        response = NextResponse.next({ request: { headers } });
        await refreshProxySession(request, response, config.ADMIN_CONSOLE_SESSION_SECRET, identity);
      } catch (error) {
        if (error instanceof AdminApiError && error.status === 401) {
          response = NextResponse.redirect(new URL("/login", request.url));
          (await proxySession(request, response, config.ADMIN_CONSOLE_SESSION_SECRET)).destroy();
        } else
          response = new NextResponse("The gateway is unavailable. Please reload to try again.", {
            status: 503,
          });
      }
    }
  }
  response.headers.set("Content-Security-Policy", policy);
  response.headers.set("Referrer-Policy", "no-referrer");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Cache-Control", "no-store");
  return response;
}
async function proxySession(request: NextRequest, response: NextResponse, password: string) {
  return getIronSession<SessionData>(
    nextProxyCookies(request, response),
    sessionOptions(password, readConfig().DEMO_MODE),
  );
}

async function refreshProxySession(
  request: NextRequest,
  response: NextResponse,
  password: string,
  identity: Awaited<ReturnType<typeof fetchIdentity>>,
) {
  const refreshed = await proxySession(request, response, password);
  refreshed.lastSeen = Date.now();
  refreshed.identity = identity;
  await refreshed.save();
}

function createCsp(nonce: string) {
  const developmentEval = process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : "";
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${developmentEval}`,
    `style-src 'self' 'nonce-${nonce}'`,
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
