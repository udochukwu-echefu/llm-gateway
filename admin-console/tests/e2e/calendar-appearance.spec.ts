import { test, expect, signIn, setTheme } from "./fixtures";
import {
  calendarData,
  calendarEvidence,
  chooseCalendarPreset,
  openCalendar,
  settleCalendar,
  submitCalendarFilters,
} from "./calendar-controls";
import { weekdayContrast } from "./calendar-contrast";

for (const view of [
  { name: "desktop-light", theme: "light", width: 1440, height: 1050 },
  { name: "desktop-dark", theme: "dark", width: 1440, height: 1050 },
  { name: "tablet", theme: "light", width: 820, height: 1180 },
  { name: "phone", theme: "dark", width: 375, height: 900 },
]) {
  test(`calendar weekday contrast, focus and positioning / ${view.name}`, async ({
    page,
    credentials,
  }) => {
    await page.setViewportSize({ width: view.width, height: view.height });
    await signIn(page, credentials.platform);
    await page.clock.setFixedTime(new Date(calendarData.now));
    await setTheme(page, view.theme);
    await page.goto(`/analytics?org=${encodeURIComponent(calendarData.org)}`);
    await chooseCalendarPreset(page, "Last 7 days");
    await submitCalendarFilters(page, "/analytics");
    const calendar = await openCalendar(page);
    await settleCalendar(page);

    const contrast = await weekdayContrast(page);
    await calendarEvidence(page, `calendar-${view.name}`, contrast);
    console.log(`Calendar ${view.name}: ${JSON.stringify(contrast)}`);
    expect(contrast.ratio).toBeGreaterThanOrEqual(4.5);
    const dimensions = await calendar.evaluate((element) => {
      const box = element.getBoundingClientRect();
      return {
        left: box.left,
        top: box.top,
        right: box.right,
        bottom: box.bottom,
        width: innerWidth,
        height: innerHeight,
        scroll: element.scrollWidth,
        client: element.clientWidth,
        pageScroll: document.documentElement.scrollWidth,
      };
    });
    expect(dimensions.left).toBeGreaterThanOrEqual(0);
    expect(dimensions.top).toBeGreaterThanOrEqual(0);
    expect(dimensions.right).toBeLessThanOrEqual(dimensions.width);
    expect(dimensions.bottom).toBeLessThanOrEqual(dimensions.height);
    expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client);
    expect(dimensions.pageScroll).toBeLessThanOrEqual(dimensions.width);
    await page.keyboard.press("ArrowRight");
    const focused = calendar.locator("button:focus-visible");
    await expect(focused).toHaveCount(1);
    const focus = await focused.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        width: parseFloat(style.outlineWidth),
        style: style.outlineStyle,
        color: style.outlineColor,
      };
    });
    expect(focus.width).toBeGreaterThanOrEqual(2);
    expect(focus.style).toBe("solid");
    await calendar.getByLabel("End time (UTC)").fill("");
    await expect(calendar.getByRole("button", { name: "Apply", exact: true })).toBeDisabled();
    expect(
      await calendar
        .getByRole("button", { name: "Apply", exact: true })
        .evaluate((element) => parseFloat(getComputedStyle(element).opacity)),
    ).toBeLessThan(1);
    await page.keyboard.press("Escape");
    await expect(calendar).not.toBeVisible();
    await expect(page.getByRole("button", { name: "Open start date calendar" })).toBeFocused();
  });
}
