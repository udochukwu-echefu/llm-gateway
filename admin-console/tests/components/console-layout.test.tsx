import { expect, test, vi } from "vitest";
import ConsoleLayout from "@/app/(console)/layout";

const mocks = vi.hoisted(() => ({ config: vi.fn(), headers: vi.fn() }));
vi.mock("@/lib/config", () => ({ readConfig: mocks.config }));
vi.mock("next/headers", () => ({ headers: mocks.headers }));
vi.mock("@/components/shell", () => ({ Shell: () => null }));

for (const [enabled, key, org] of [
  [false, "private-key-sentinel", false],
  [true, undefined, false],
  [true, "private-key-sentinel", true],
] as const) {
  test(`layout serializes only safe availability booleans (${enabled}, ${org})`, async () => {
    const identity = { key_id: "public-id", name: "Test", role: "viewer", organization: null };
    mocks.headers.mockResolvedValue(
      new Headers({ "x-console-identity": JSON.stringify(identity) }),
    );
    mocks.config.mockReturnValue({
      DEMO_MODE: enabled,
      DEMO_ORG_VIEWER_KEY: key,
      DEMO_VIEWER_KEY: "private-platform-sentinel",
      ADMIN_CONSOLE_SESSION_SECRET: "private-session-sentinel",
    });

    const layout = await ConsoleLayout({ children: "Content" });

    expect(layout.props).toEqual({ identity, demo: { enabled, org }, children: "Content" });
    expect(JSON.stringify(layout.props)).not.toContain("private-");
  });
}
