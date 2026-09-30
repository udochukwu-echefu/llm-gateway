import "server-only";
import { redactCredentials } from "./admin-client";
// Strip upstream headers, redact credential-shaped text, and release only the first key creation secret.
export function browserResponse(body: unknown, permitsKey: boolean): unknown {
  if (typeof body === "string")
    return redactCredentials(body);
  if (Array.isArray(body))
    return body.map((item) => browserResponse(item, false));
  if (body && typeof body === "object")
    return Object.fromEntries(Object.entries(body).filter(([key]) => key !== "secret_hash" && (key !== "key" || permitsKey)).map(([key, value]) => [key, key === "key" && permitsKey && typeof value === "string" && /^lgw_[a-z2-7]{12}_[A-Za-z0-9_-]+$/.test(value) ? value : browserResponse(value, false)]));
  return body;
}
