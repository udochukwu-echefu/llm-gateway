// Prefix dangerous spreadsheet expressions even when hidden behind whitespace.
export function csvCell(value: unknown): string {
  const raw =
    value == null ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
  const safe = /^[\s\u0000-\u001f]*[=+\-@]/.test(raw) ? "'" + raw : raw;
  return '"' + safe.replace(/"/g, '""') + '"';
}
export function csvRow(values: unknown[]) {
  return values.map(csvCell).join(",") + "\r\n";
}
export const EXPORT_CAP = 10000;
