import "server-only";
import { z } from "zod";
export class AdminApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export function redactCredentials(text: string): string {
  return text.replace(/lgwa_[A-Za-z0-9_-]+/g, "[redacted admin credential]").replace(/lgw_[a-z2-7]{12}_[A-Za-z0-9_-]+/g, "[redacted tenant credential]");
}
export async function adminRequest<T>(base: string, key: string, path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${base.replace(/\/$/, "")}/admin/v1${path}`, {
      ...init, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(15000),
      headers: { ...init.headers, Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    });
  }
  catch {
    throw new AdminApiError(503, "The gateway is unavailable. Please try again.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const parsed = z.object({ error: z.object({ message: z.string() }) }).safeParse(body);
    throw new AdminApiError(response.status, parsed.success ? redactCredentials(parsed.data.error.message) : "The gateway could not complete this request.");
  }
  return body as T;
}
