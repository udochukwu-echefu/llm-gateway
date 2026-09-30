import { describe, expect, test } from "vitest";
import { getIronSession } from "iron-session";
import {
  ABSOLUTE_MS,
  IDLE_MS,
  isActive,
  sessionOptions,
  type SessionData,
} from "@/lib/session-policy";
const password = "obviously-fake-test-session-secret-at-least-32-bytes";
const identity = {
  key_id: "fakepublicid",
  name: "Fake admin",
  role: "platform" as const,
  organization: null,
};
function store(value = "") {
  const values = new Map<string, string>();
  if (value) values.set(sessionOptions(password).cookieName, value);
  return {
    values,
    get: (name: string) => (values.has(name) ? { name, value: values.get(name)! } : undefined),
    set: (name: string, value: string) => {
      values.set(name, value);
    },
  };
}
describe("encrypted session", () => {
  test("round trip encrypts the credential and has secure cookie flags", async () => {
    const cookies = store();
    const session = await getIronSession<SessionData>(cookies, sessionOptions(password));
    Object.assign(session, {
      adminKey: "lgwa_obviously_fake_for_unit_test",
      identity,
      issuedAt: 1000,
      lastSeen: 1000,
    });
    await session.save();
    const sealed = cookies.values.get(sessionOptions(password).cookieName)!;
    expect(sealed.includes("lgwa_")).toBe(false);
    const restored = await getIronSession<SessionData>(store(sealed), sessionOptions(password));
    expect(restored.adminKey === session.adminKey).toBe(true);
    expect(isActive(restored, 2000)).toBe(true);
    expect(sessionOptions(password).cookieOptions).toMatchObject({
      httpOnly: true,
      secure: true,
      sameSite: "strict",
      path: "/",
    });
  });
  test("tampered cookie cannot authenticate", async () => {
    const cookies = store();
    const session = await getIronSession<SessionData>(cookies, sessionOptions(password));
    Object.assign(session, {
      adminKey: "lgwa_fake_test",
      identity,
      issuedAt: 1000,
      lastSeen: 1000,
    });
    await session.save();
    const sealed = cookies.values.get(sessionOptions(password).cookieName)!;
    const restored = await getIronSession<SessionData>(
      store(sealed.slice(0, 20) + "tampered" + sealed.slice(28)),
      sessionOptions(password),
    );
    expect(isActive(restored, 2000)).toBe(false);
  });
  test("absolute expiry cannot be extended by activity", () => {
    expect(
      isActive(
        { adminKey: "fake", identity, issuedAt: 1000, lastSeen: 1000 + ABSOLUTE_MS - 1 },
        1000 + ABSOLUTE_MS,
      ),
    ).toBe(false);
  });
  test("idle expiry and future timestamps are rejected", () => {
    const session = { adminKey: "fake", identity, issuedAt: 1000, lastSeen: 1000 };
    expect(isActive(session, 1000 + IDLE_MS - 1)).toBe(true);
    expect(isActive(session, 1000 + IDLE_MS)).toBe(false);
    expect(isActive(session, 999)).toBe(false);
    expect(isActive({})).toBe(false);
  });
});
