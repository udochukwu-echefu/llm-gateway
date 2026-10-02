import { test, expect, signIn } from "./fixtures";
import {
  calendarData,
  calendarEvidence,
  chooseCalendarPreset,
  expectAttempts,
  expectBounds,
  openCalendar,
  submitCalendarFilters,
} from "./calendar-controls";

test.use({ timezoneId: "America/Los_Angeles" });
test.beforeEach(async ({ page, credentials }) => {
  await signIn(page, credentials.platform);
  await page.clock.setFixedTime(new Date(calendarData.now));
});

for (const [preset, date, prefix] of [
  ["Today", "2026-10-02", "calendar-today"],
  ["Yesterday", "2026-10-01", "calendar-yesterday"],
]) {
  test(`Requests / ${preset} includes the final microsecond but not next midnight`, async ({
    page,
  }) => {
    await page.goto(`/requests?org=${encodeURIComponent(calendarData.org)}`);
    await page.getByText("Request filters", { exact: true }).click();

    await chooseCalendarPreset(page, preset);
    const result = await submitCalendarFilters(page, "/requests");
    await expect(page.locator(".request-table tbody tr")).toHaveCount(result.body.data.length);
    await calendarEvidence(page, `requests-${preset.toLowerCase()}`, {
      browser: page.url(),
      http: result.url.href,
      body: result.body,
    });

    await expectBounds(page, result.url, `${date}T00:00:00.000Z`, `${date}T23:59:59.999999Z`);
    const ids = calendarData.attempts
      .filter((attempt) => attempt.id.startsWith(prefix))
      .map((attempt) => attempt.id);
    expect(result.body.data.map((row: { request_id: string }) => row.request_id).sort()).toEqual(
      [...ids].sort(),
    );
    await expectAttempts(page, ids);
    await page.reload();
    await page.getByText("Request filters", { exact: true }).click();
    await expect(page.getByLabel("To timestamp (UTC)")).toHaveValue(`${date}T23:59:59.999999`);
    const calendar = await openCalendar(page);
    await expect(calendar.getByRole("button", { name: preset, exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(calendar.getByLabel("End time (UTC)")).toHaveValue("23:59:59.999999");
    await expect(calendar.locator(".calendar-count")).toContainText("23:59:59.999999 UTC");
    await calendar.getByRole("button", { name: "Apply", exact: true }).click();
    const url = page.url();
    await page.getByRole("button", { name: "Apply filters" }).click();
    await expect(page).toHaveURL(url);
    await expectAttempts(page, ids);
  });
}

test("Analytics / Last 7 days counts seven whole UTC dates, including late records", async ({
  page,
}) => {
  await page.goto(
    `/analytics?org=${encodeURIComponent(calendarData.org)}&group_by=provider&bucket=day`,
  );

  await chooseCalendarPreset(page, "Last 7 days");
  const result = await submitCalendarFilters(page, "/analytics");
  await expect(page.locator(".analytics-table tbody tr")).toHaveCount(result.body.data.length);
  await calendarEvidence(page, "analytics-last-7-days", {
    browser: page.url(),
    http: result.url.href,
    body: result.body,
  });

  await expectBounds(page, result.url, "2026-09-26T00:00:00.000Z", "2026-10-02T23:59:59.999999Z");
  const included = calendarData.attempts.filter(
    (attempt) => attempt.at.slice(0, 10) >= "2026-09-26" && attempt.at.slice(0, 10) <= "2026-10-02",
  );
  expect(
    result.body.data.reduce((sum: number, row: { requests: number }) => sum + row.requests, 0),
  ).toBe(included.length);
  for (const row of result.body.data) {
    const count = included.filter(
      (attempt) => attempt.at.slice(0, 10) === row.bucket.slice(0, 10),
    ).length;
    expect(row.requests).toBe(count);
    const displayed = page.locator(".analytics-table tbody tr").filter({ hasText: row.bucket });
    await expect(displayed.getByRole("cell").nth(2)).toHaveText(String(count));
  }
  const requests = await page.evaluate(
    async (bounds) => {
      const query = new URLSearchParams(bounds);
      const response = await fetch(`/api/admin/orgs/Calendar%20fixtures/requests?${query}`);
      return { status: response.status, body: await response.json() };
    },
    { since: result.url.searchParams.get("since")!, until: result.url.searchParams.get("until")! },
  );
  expect(requests.status).toBe(200);
  expect(requests.body.data.map((row: { request_id: string }) => row.request_id).sort()).toEqual(
    included.map((attempt) => attempt.id).sort(),
  );
  await page.reload();
  const calendar = await openCalendar(page);
  await expect(calendar.getByLabel("End time (UTC)")).toHaveValue("23:59:59.999999");
  await calendar.getByRole("button", { name: "Apply", exact: true }).click();
  const url = page.url();
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(url);
});

test("custom keyboard-selected dates and explicit times remain exact after URL reload and reapply", async ({
  page,
}) => {
  await page.goto(`/requests?org=${encodeURIComponent(calendarData.org)}`);
  await page.getByText("Request filters", { exact: true }).click();
  const calendar = await openCalendar(page);
  const today = calendar.locator('[data-date="2026-10-02"]');

  await today.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(calendar.locator('[data-date="2026-10-01"]')).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter");
  await calendar.getByLabel("Start time (UTC)").fill("23:59:59.999999");
  await calendar.getByLabel("End time (UTC)").fill("09:30:15.123456");
  await expect(calendar.getByRole("button", { name: "This month", exact: true })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await calendar.getByRole("button", { name: "Apply", exact: true }).click();
  const result = await submitCalendarFilters(page, "/requests");

  await expectBounds(
    page,
    result.url,
    "2026-10-01T23:59:59.999999Z",
    "2026-10-02T09:30:15.123456Z",
  );
  const ids = ["calendar-yesterday-fraction", "calendar-today-start", "calendar-today-custom"];
  await expectAttempts(page, ids);
  await page.reload();
  await page.getByText("Request filters", { exact: true }).click();
  const reopened = await openCalendar(page);
  await expect(reopened.getByLabel("Start time (UTC)")).toHaveValue("23:59:59.999999");
  await expect(reopened.getByLabel("End time (UTC)")).toHaveValue("09:30:15.123456");
  await reopened.getByRole("button", { name: "Apply", exact: true }).click();
  const url = page.url();
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(url);
  await expectAttempts(page, ids);
});

test("manual edits override presets; Cancel, Escape, Clear and rolling quick ranges retain their behavior", async ({
  page,
}) => {
  await page.goto(`/requests?org=${encodeURIComponent(calendarData.org)}`);
  await page.getByText("Request filters", { exact: true }).click();
  await chooseCalendarPreset(page, "Today");
  const calendar = await openCalendar(page);
  await calendar.getByLabel("Start time (UTC)").fill("09:30");
  await calendar.getByLabel("End time (UTC)").fill("23:59");
  await expect(calendar.getByRole("button", { name: "Today", exact: true })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await calendar.getByRole("button", { name: "Apply", exact: true }).click();
  let result = await submitCalendarFilters(page, "/requests");
  await expectBounds(page, result.url, "2026-10-02T09:30:00.000Z", "2026-10-02T23:59:00.000Z");
  await expectAttempts(page, ["calendar-today-custom", "calendar-today-minute"]);
  const url = page.url();
  for (const dismissal of ["Cancel", "Escape"]) {
    const draft = await openCalendar(page);
    await draft.getByRole("button", { name: "Yesterday", exact: true }).click();
    if (dismissal === "Escape") await page.keyboard.press("Escape");
    else await draft.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(draft).not.toBeVisible();
    await expect(page.getByRole("button", { name: "Open start date calendar" })).toBeFocused();
    await expect(page.getByLabel("To timestamp (UTC)")).toHaveValue("2026-10-02T23:59:00.000");
    await expect(page).toHaveURL(url);
  }
  const clear = await openCalendar(page);
  await clear.getByRole("button", { name: "Clear dates", exact: true }).click();
  await expect(page.getByLabel("From timestamp (UTC)")).toHaveValue("");
  await expect(page.getByLabel("To timestamp (UTC)")).toHaveValue("");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect.poll(() => new URL(page.url()).searchParams.has("until")).toBe(false);
  await expectAttempts(
    page,
    calendarData.attempts.map((attempt) => attempt.id),
  );
  const response = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.startsWith("/api/admin/") &&
      new URL(response.url()).pathname.endsWith("/requests") &&
      new URL(response.url()).searchParams.has("since"),
  );
  await page.getByRole("button", { name: "15m", exact: true }).click();
  const quick = await response;
  result = { url: new URL(quick.url()), body: await quick.json() };
  await expectBounds(page, result.url, "2026-10-02T00:15:45.123Z", calendarData.now);
});

test("Audit calendar presets submit date-only UTC values and preserve the existing whole-date results", async ({
  page,
}) => {
  await page.goto("/audit?actor=synthetic-console-fixture");
  const baseline = await page.evaluate(async () =>
    (await fetch("/api/admin/audit?actor=synthetic-console-fixture&page_size=100")).json(),
  );
  expect(baseline.data.length).toBeGreaterThan(0);
  const date = baseline.data[0].occurred_at.slice(0, 10);
  await page.clock.setFixedTime(new Date(`${date}T00:30:00Z`));

  const calendar = await openCalendar(page);
  await expect(calendar.getByLabel("Start time (UTC)")).toHaveCount(0);
  await calendar.getByRole("button", { name: "Today", exact: true }).click();
  await calendar.getByRole("button", { name: "Apply", exact: true }).click();
  const result = await submitCalendarFilters(page, "/audit");

  await expectBounds(page, result.url, date, date);
  expect(result.body.total).toBe(baseline.total);
  expect(result.body.data.map((row: { id: number }) => row.id)).toEqual(
    baseline.data.slice(0, 25).map((row: { id: number }) => row.id),
  );
  await expect(page.getByLabel("From date (UTC)")).toHaveValue(date);
  await page.reload();
  const reopened = await openCalendar(page);
  await expect(reopened.getByRole("button", { name: "Today", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await reopened.getByRole("button", { name: "Clear dates", exact: true }).click();
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect.poll(() => new URL(page.url()).searchParams.has("since")).toBe(false);
});
