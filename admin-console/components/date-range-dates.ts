// Calendar-only UTC arithmetic. API timestamp conversion stays in FilterBar.
export interface CalendarRange {
  start: string;
  end: string;
}
const dayMilliseconds = 86400000;
const firstDay = "0001-01-01";
const lastDay = "9999-12-31";

export function calendarDate(key: string): Date {
  return new Date(`${key}T00:00:00.000Z`);
}
export function dateKey(date: Date): string {
  return date.toISOString().slice(0, 10);
}
export function validDateKey(value: string): string | undefined {
  const key = value.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(key) || key < firstDay || key > lastDay) return;
  const date = calendarDate(key);
  return Number.isFinite(date.getTime()) && dateKey(date) === key ? key : undefined;
}
export function addCalendarDays(key: string, amount: number): string {
  const time = Math.max(
    calendarDate(firstDay).getTime(),
    Math.min(
      calendarDate(lastDay).getTime(),
      calendarDate(key).getTime() + amount * dayMilliseconds,
    ),
  );
  return dateKey(new Date(time));
}
export function monthStart(key: string): string {
  return `${key.slice(0, 7)}-01`;
}
export function addCalendarMonths(key: string, amount: number): string {
  const date = calendarDate(monthStart(key));
  date.setUTCMonth(date.getUTCMonth() + amount);
  if (date.getUTCFullYear() < 1) return firstDay;
  if (date.getUTCFullYear() > 9999) return monthStart(lastDay);
  return dateKey(date);
}
export function shiftCalendarMonth(key: string, amount: number): string {
  const month = addCalendarMonths(key, amount);
  const last = month === "9999-12-01" ? lastDay : addCalendarDays(addCalendarMonths(month, 1), -1);
  return `${month.slice(0, 7)}-${String(Math.min(calendarDate(key).getUTCDate(), calendarDate(last).getUTCDate())).padStart(2, "0")}`;
}
export function orderCalendarRange(start: string, end: string): CalendarRange {
  return start <= end ? { start, end } : { start: end, end: start };
}
export function rangeFromValues(start: string, end: string): CalendarRange | null {
  const from = validDateKey(start);
  const to = validDateKey(end);
  return from || to ? orderCalendarRange(from ?? to!, to ?? from!) : null;
}
export function calendarDayCount(range: CalendarRange): number {
  return (
    Math.round(
      (calendarDate(range.end).getTime() - calendarDate(range.start).getTime()) / dayMilliseconds,
    ) + 1
  );
}
export function formatCalendarDate(key: string, options: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat("en-US", { ...options, timeZone: "UTC" }).format(
    calendarDate(key),
  );
}
export function formatCalendarRange(range: CalendarRange): string {
  const formatter = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
  return range.start === range.end
    ? formatter.format(calendarDate(range.start))
    : formatter.formatRange(calendarDate(range.start), calendarDate(range.end));
}
export function calendarPresets(today: string): { label: string; range: CalendarRange }[] {
  const previousMonth = addCalendarMonths(today, -1);
  const quarterMonth = String(Math.floor(calendarDate(today).getUTCMonth() / 3) * 3 + 1).padStart(
    2,
    "0",
  );
  return [
    { label: "Today", range: { start: today, end: today } },
    {
      label: "Yesterday",
      range: { start: addCalendarDays(today, -1), end: addCalendarDays(today, -1) },
    },
    { label: "Last 7 days", range: { start: addCalendarDays(today, -6), end: today } },
    { label: "Last 30 days", range: { start: addCalendarDays(today, -29), end: today } },
    { label: "This month", range: { start: monthStart(today), end: today } },
    {
      label: "Last month",
      range: { start: previousMonth, end: addCalendarDays(monthStart(today), -1) },
    },
    {
      label: "This quarter",
      range: { start: `${today.slice(0, 4)}-${quarterMonth}-01`, end: today },
    },
    { label: "Year to date", range: { start: `${today.slice(0, 4)}-01-01`, end: today } },
  ];
}
