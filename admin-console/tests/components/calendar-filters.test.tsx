import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { FilterBar } from "@/components/list-controls";

const navigation = vi.hoisted(() => ({ push: vi.fn(), params: "org=Calendar" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.params),
  usePathname: () => "/requests",
  useRouter: () => ({ push: navigation.push }),
}));
const fields = [
  { name: "since", label: "From timestamp (UTC)", type: "datetime" },
  { name: "until", label: "To timestamp (UTC)", type: "datetime" },
];
beforeEach(() => {
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
  }));
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-02T00:30:45.123Z"));
  navigation.params = "org=Calendar";
  navigation.push.mockClear();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test.each([
  ["Today", "2026-10-02", "2026-10-02"],
  ["Yesterday", "2026-10-01", "2026-10-01"],
  ["Last 7 days", "2026-09-26", "2026-10-02"],
  ["Last 30 days", "2026-09-03", "2026-10-02"],
  ["This month", "2026-10-01", "2026-10-02"],
  ["Last month", "2026-09-01", "2026-09-30"],
  ["This quarter", "2026-10-01", "2026-10-02"],
  ["Year to date", "2026-01-01", "2026-10-02"],
])("%s resets manual times to inclusive whole UTC days", async (preset, start, end) => {
  const user = userEvent.setup();
  navigation.params += "&since=2026-09-01T09%3A30%3A00Z&until=2026-09-02T17%3A45%3A00Z";
  render(<FilterBar fields={fields} />);

  await user.click(screen.getByRole("button", { name: "Open start date calendar" }));
  const calendar = within(screen.getByRole("dialog", { name: "Date range" }));
  await user.click(calendar.getByRole("button", { name: preset }));
  expect((calendar.getByLabelText("Start time (UTC)") as HTMLInputElement).value).toBe("00:00");
  expect((calendar.getByLabelText("End time (UTC)") as HTMLInputElement).value).toBe(
    "23:59:59.999999",
  );
  await user.click(calendar.getByRole("button", { name: "Apply" }));
  await user.click(screen.getByRole("button", { name: "Apply filters" }));

  const url = new URL(navigation.push.mock.lastCall![0], "http://fake.test");
  expect(url.searchParams.get("since")).toBe(`${start}T00:00:00.000Z`);
  expect(url.searchParams.get("until")).toBe(`${end}T23:59:59.999999Z`);
});

test("URL microseconds and offset timestamps survive calendar reopening and unchanged submission", async () => {
  const user = userEvent.setup();
  navigation.params +=
    "&since=2026-10-02T01%3A30%3A15.123456%2B01%3A00&until=2026-10-02T23%3A59%3A59.999999Z";
  render(<FilterBar fields={fields} />);

  expect((screen.getByLabelText("From timestamp (UTC)") as HTMLInputElement).value).toBe(
    "2026-10-02T00:30:15.123456",
  );
  await user.click(screen.getByRole("button", { name: "Open end date calendar" }));
  const calendar = within(screen.getByRole("dialog", { name: "Date range" }));
  expect((calendar.getByLabelText("Start time (UTC)") as HTMLInputElement).value).toBe(
    "00:30:15.123456",
  );
  expect((calendar.getByLabelText("End time (UTC)") as HTMLInputElement).value).toBe(
    "23:59:59.999999",
  );
  await user.click(calendar.getByRole("button", { name: "Apply" }));
  await user.click(screen.getByRole("button", { name: "Apply filters" }));

  const url = new URL(navigation.push.mock.lastCall![0], "http://fake.test");
  expect(url.searchParams.get("since")).toBe("2026-10-02T00:30:15.123456Z");
  expect(url.searchParams.get("until")).toBe("2026-10-02T23:59:59.999999Z");
});

test("invalid UTC date text prevents filter submission", async () => {
  const user = userEvent.setup();
  render(<FilterBar fields={fields} />);

  await user.type(screen.getByLabelText("From timestamp (UTC)"), "2026-02-30T09:30");
  await user.click(screen.getByRole("button", { name: "Apply filters" }));

  expect(navigation.push).not.toHaveBeenCalled();
});

test("a preset replaces invalid typed dates and restores a submittable filter", async () => {
  const user = userEvent.setup();
  render(<FilterBar fields={fields} />);
  await user.type(screen.getByLabelText("From timestamp (UTC)"), "2026-02-30T09:30");
  await user.click(screen.getByRole("button", { name: "Open start date calendar" }));
  const calendar = within(screen.getByRole("dialog", { name: "Date range" }));

  await user.click(calendar.getByRole("button", { name: "Today" }));
  await user.click(calendar.getByRole("button", { name: "Apply" }));
  await user.click(screen.getByRole("button", { name: "Apply filters" }));

  const url = new URL(navigation.push.mock.lastCall![0], "http://fake.test");
  expect(url.searchParams.get("since")).toBe("2026-10-02T00:00:00.000Z");
  expect(url.searchParams.get("until")).toBe("2026-10-02T23:59:59.999999Z");
});
