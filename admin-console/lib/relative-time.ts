export function relativeTime(value: string, now = Date.now()) {
  const delta = Date.parse(value) - now;
  if (!Number.isFinite(delta)) return "Unknown";
  const seconds = Math.round(delta / 1000);
  for (const [unit, size] of [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
    ["second", 1],
  ] as const) {
    if (Math.abs(seconds) >= size || unit === "second")
      return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(
        Math.round(seconds / size),
        unit,
      );
  }
  return "Unknown";
}
export function absoluteTime(value: string, zone: "utc" | "local") {
  const timezone = zone === "utc" ? "UTC" : Intl.DateTimeFormat().resolvedOptions().timeZone;
  return (
    new Intl.DateTimeFormat("en-GB", {
      dateStyle: "medium",
      timeStyle: "medium",
      timeZone: timezone,
    }).format(new Date(value)) +
    " " +
    timezone
  );
}
