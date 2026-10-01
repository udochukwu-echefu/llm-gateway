import { pico } from "./money";
export function updateQuery(current: string, changes: Record<string, string | null>) {
  const next = new URLSearchParams(current);
  for (const [key, value] of Object.entries(changes)) {
    if (value) next.set(key, value);
    else next.delete(key);
  }
  return next.toString();
}
export function listSort<T>(rows: T[], column: keyof T, direction: string) {
  return [...rows].sort((a, b) => {
    const left = a[column],
      right = b[column];
    if (left == null) return right == null ? 0 : 1;
    if (right == null) return -1;
    const isMoney =
      String(column).endsWith("_usd") && typeof left === "string" && typeof right === "string";
    const compared = isMoney
      ? pico(String(left)) === pico(String(right))
        ? 0
        : pico(String(left)) > pico(String(right))
          ? 1
          : -1
      : typeof left === "number" && typeof right === "number"
        ? left - right
        : String(left).localeCompare(String(right));
    return direction === "desc" ? -compared : compared;
  });
}
