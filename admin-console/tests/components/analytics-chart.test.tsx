import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { AnalyticsChart } from "@/components/analytics-chart";
import type { AnalyticsRow } from "@/lib/console-contracts";

const row: AnalyticsRow = {
  bucket: "2026-10-01T00:00:00Z",
  group: "groq",
  requests: 1234,
  error_rate: 0.3333333333333333,
  duration_p50: 880.0000000000001,
  duration_p95: 1724.9999999999998,
  duration_p99: 24200.000000000004,
  ttfb_p50: null,
  ttfb_p95: null,
  ttfb_p99: null,
  fallback_count: 0,
  retry_count: 0,
  cache_hit_rate: 0,
  saved_usd: null,
  redaction_count: null,
};

test("legend keyboard toggles remove the slow series and rescale the axis", async () => {
  const user = userEvent.setup();
  render(
    <AnalyticsChart
      rows={[row, { ...row, group: "nvidia", duration_p95: 55000 }]}
      bucket="day"
      measure="duration_p95"
    />,
  );
  const chart = screen.getByRole("img");
  expect(chart.getAttribute("data-axis-maximum")).toBe("55000");
  expect(chart.textContent).toContain("55.0 s");
  expect(chart.querySelector("circle title")?.textContent).toContain("1,725 ms");
  const nvidia = screen.getByRole("button", { name: "nvidia" });
  nvidia.focus();
  await user.keyboard(" ");
  expect(nvidia.getAttribute("aria-pressed")).toBe("false");
  expect(chart.getAttribute("data-axis-maximum")).toBe(String(row.duration_p95));
  expect(chart.querySelectorAll("circle")).toHaveLength(1);
  await user.keyboard("{Enter}");
  expect(nvidia.getAttribute("aria-pressed")).toBe("true");
  expect(chart.getAttribute("data-axis-maximum")).toBe("55000");
});

test("log latency has labelled decade ticks, unknown and zero gaps, and a distinct scale", async () => {
  const user = userEvent.setup();
  render(
    <AnalyticsChart
      rows={[
        row,
        { ...row, group: "nvidia", duration_p95: 50599.99999999999 },
        { ...row, group: "unknown", duration_p95: null },
        { ...row, group: "zero", duration_p95: 0 },
      ]}
      bucket="day"
      measure="duration_p95"
    />,
  );
  const chart = screen.getByRole("img");
  const linearY = Number(chart.querySelector("circle")?.getAttribute("cy"));
  await user.click(screen.getByRole("checkbox", { name: "Log scale" }));
  expect(chart.getAttribute("data-axis-scale")).toBe("log");
  expect(Number(chart.querySelector("circle")?.getAttribute("cy"))).toBeLessThan(linearY);
  expect(chart.textContent).toContain("1 ms");
  expect(chart.textContent).toContain("10.0 s");
  expect(chart.textContent).toContain("50.6 s");
  expect(chart.querySelectorAll("circle")).toHaveLength(2);
  expect(chart.innerHTML).not.toMatch(/NaN|Infinity/);
});

test("rate and count chart ticks and tooltips use the shared formatter", () => {
  const { rerender } = render(<AnalyticsChart rows={[row]} bucket="day" measure="error_rate" />);
  expect(screen.queryByRole("checkbox", { name: "Log scale" })).toBeNull();
  expect(screen.getByRole("img").querySelector("circle title")?.textContent).toContain("33.3%");
  rerender(<AnalyticsChart rows={[row]} bucket="day" measure="requests" />);
  expect(screen.getByRole("img").textContent).toContain("1,234");
});

test("hiding every series leaves a finite empty axis", async () => {
  const user = userEvent.setup();
  render(<AnalyticsChart rows={[row]} bucket="day" measure="duration_p95" />);
  await user.click(screen.getByRole("button", { name: "groq" }));
  expect(screen.getByRole("img").querySelectorAll("circle")).toHaveLength(0);
  expect(screen.getByRole("img").innerHTML).not.toMatch(/NaN|Infinity/);
});

test("positive sub-millisecond latency remains inside the logarithmic plot", async () => {
  const user = userEvent.setup();
  render(
    <AnalyticsChart rows={[{ ...row, duration_p95: 0.1 }]} bucket="day" measure="duration_p95" />,
  );
  await user.click(screen.getByRole("checkbox", { name: "Log scale" }));
  const chart = screen.getByRole("img");
  expect(chart.textContent).toContain("0.1 ms");
  const position = Number(chart.querySelector("circle")?.getAttribute("cy"));
  expect(position).toBeGreaterThanOrEqual(40);
  expect(position).toBeLessThanOrEqual(220);
});
