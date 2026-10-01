import { pico } from "./money";

type Numeric = number | string | null | undefined;
export function numericValue(value: Numeric): number | null {
  if (value == null || (typeof value === "string" && !value.trim())) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
export function formatDuration(value: Numeric): string {
  const number = numericValue(value);
  if (number === null) return "Unknown";
  return number < 10000
    ? `${Math.round(number).toLocaleString("en-US")} ms`
    : `${(number / 1000).toFixed(1)} s`;
}
export function formatRate(value: Numeric): string {
  const number = numericValue(value);
  return number === null ? "Unknown" : `${(number * 100).toFixed(1)}%`;
}
export function formatCount(value: Numeric): string {
  const number = numericValue(value);
  return number === null ? "Unknown" : Math.round(number).toLocaleString("en-US");
}
export function formatMeasure(measure: string, value: Numeric): string {
  if (measure.includes("rate")) return formatRate(value);
  if (measure.startsWith("duration") || measure.startsWith("ttfb")) return formatDuration(value);
  return formatCount(value);
}
export function csvNumber(value: number): string {
  return Number.isFinite(value) ? String(Number(value.toFixed(3))) : "";
}
// Round decimal money without converting its exact stored value to a float.
export function csvDecimal(value: string | null): string {
  if (value === null) return "";
  const rounded = (pico(value) + 500000000n) / 1000000000n;
  return `${rounded / 1000n}.${(rounded % 1000n).toString().padStart(3, "0")}`;
}

// Log ticks must label positive sub-millisecond decades instead of rounding them to zero.
export function formatLatencyTick(value: number): string {
  return value > 0 && value < 1
    ? `${value.toLocaleString("en-US", { maximumSignificantDigits: 1 })} ms`
    : formatDuration(value);
}
