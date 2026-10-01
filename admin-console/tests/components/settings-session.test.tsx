import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Settings } from "@/components/settings";
import { ABSOLUTE_MS, DEMO_ABSOLUTE_MS } from "@/lib/session-policy";

vi.mock("@/components/preferences", () => ({
  usePreferences: () => ({ value: { theme: "system", timeDisplay: "local" }, update: vi.fn() }),
}));
vi.mock("@/components/record-time", () => ({
  RecordTime: ({ value }: { value: string }) => <span>{value}</span>,
}));
for (const demo of [false, true]) {
  test(`viewer Settings shows actual ${demo ? "demo" : "ordinary"} session lifetime`, () => {
    const issuedAt = 100000;
    render(
      <Settings
        identity={{
          key_id: "fake",
          name: "Viewer",
          role: "viewer",
          organization: { id: "fake", name: "Northwind Health" },
        }}
        issuedAt={issuedAt}
        lastSeen={issuedAt}
        demo={demo}
      />,
    );
    expect(
      screen.getByText(new Date(issuedAt + (demo ? DEMO_ABSOLUTE_MS : ABSOLUTE_MS)).toISOString()),
    ).toBeTruthy();
  });
}
