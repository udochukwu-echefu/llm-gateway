import { expect, test, vi } from "vitest";
import { csvStream } from "@/lib/csv-stream";
import { EXPORT_CAP } from "@/lib/csv";
vi.mock("@/lib/admin-client", () => ({
  adminRequest: vi.fn(),
  redactCredentials: (value: string) =>
    value.replace(/lgwa_[A-Za-z0-9_-]+/g, "[redacted admin credential]"),
}));
test("CSV stream caps rows and never emits credentials or spreadsheet formula cells", async () => {
  const data = Array.from({ length: EXPORT_CAP + 1 }, (_, index) => ({
    request_id: index === 0 ? "=FAKE_FORMULA" : `fake-${index}`,
    cost_usd: "0.000000000001",
    alias: index === 1 ? "lgwa_FAKEONLYsecret" : "fake",
  }));
  const stream = csvStream(
    { data, next_cursor: null },
    ["request_id", "cost_usd", "alias"],
    "http://fake.test",
    "obviously-fake-server-only-key",
    "/fake",
    new URLSearchParams(),
  );
  const contents = await new Response(stream).text();
  expect(contents.split("\r\n").filter(Boolean)).toHaveLength(EXPORT_CAP + 1);
  expect(contents).toContain('"\'=FAKE_FORMULA"');
  expect(contents).not.toContain("lgwa_");
  expect(contents).toContain("0.000000000001");
});
