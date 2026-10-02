import { validDateKey } from "./date-range-dates";

export const wholeDayTimes = { start: "00:00", end: "23:59:59.999999" };
export const utcTimePattern = "(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9](?:\\.[0-9]{1,6})?)?";
export const utcTimestampPattern = `[0-9]{4}-[0-9]{2}-[0-9]{2}T${utcTimePattern}`;
export const utcTimeHint = "HH:mm or HH:mm:ss.ffffff (UTC)";
export const utcTimestampHint =
  "YYYY-MM-DDTHH:mm, with optional seconds and up to six fractional digits (UTC)";

export function validUtcTime(value: string): boolean {
  return new RegExp(`^${utcTimePattern}$`).test(value);
}
export function isWholeDayTimes(times: { start: string; end: string }): boolean {
  return /^00:00(?::00(?:\.0{1,6})?)?$/.test(times.start) && times.end === wholeDayTimes.end;
}
export function validUtcTimestamp(value: string): boolean {
  return !!validDateKey(value) && new RegExp(`^${utcTimestampPattern}$`).test(value);
}
export function timestampFieldValue(value: string): string {
  if (!value || !Number.isFinite(Date.parse(value))) return value;
  return preciseIso(value).slice(0, -1);
}
export function timestampQueryValue(value: string): string {
  return value ? preciseIso(`${value}Z`) : "";
}

function preciseIso(value: string): string {
  // Date normalizes UTC offsets but only retains milliseconds, not database microseconds.
  const iso = new Date(value).toISOString();
  const fraction = value.match(/\.(\d{1,6})(?:Z|[+-]\d{2}:\d{2})$/)?.[1];
  return fraction ? `${iso.slice(0, 19)}.${fraction}Z` : iso;
}
