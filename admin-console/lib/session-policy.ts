import type { SessionOptions } from "iron-session";
import type { Identity } from "./contracts";
export const COOKIE_NAME = "__Host-lgw-console";
export const ABSOLUTE_MS = 8 * 60 * 60 * 1000;
export const IDLE_MS = 30 * 60 * 1000;
export const DEMO_ABSOLUTE_MS = 2 * 60 * 60 * 1000;
export interface SessionData {
  adminKey?: string;
  identity?: Identity;
  issuedAt?: number;
  lastSeen?: number;
  demo?: boolean;
}
export function isActive(session: SessionData, now = Date.now()): boolean {
  const { adminKey, identity, issuedAt, lastSeen } = session;
  if (!adminKey || !identity || !issuedAt || !lastSeen) return false;
  return (
    now >= issuedAt &&
    now >= lastSeen &&
    now - issuedAt < (session.demo ? DEMO_ABSOLUTE_MS : ABSOLUTE_MS) &&
    now - lastSeen < IDLE_MS
  );
}
export function sessionOptions(password: string, demo = false): SessionOptions {
  const absolute = demo ? DEMO_ABSOLUTE_MS : ABSOLUTE_MS;
  return {
    cookieName: COOKIE_NAME,
    password,
    ttl: absolute / 1000,
    cookieOptions: {
      httpOnly: true,
      secure: true,
      sameSite: "strict",
      path: "/",
      maxAge: absolute / 1000,
    },
  };
}
