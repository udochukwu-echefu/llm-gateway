import "server-only";
import { cookies } from "next/headers";
import { getIronSession } from "iron-session";
import { readConfig } from "./config";
import { sessionOptions, type SessionData } from "./session-policy";
export async function readSession() {
  return getIronSession<SessionData>(await cookies(), sessionOptions(readConfig().ADMIN_CONSOLE_SESSION_SECRET));
}
