import "server-only";
import { adminRequest } from "./admin-client";
import { browserResponse } from "./bff-response";
import { csvRow, EXPORT_CAP } from "./csv";
import type { Page } from "./contracts";
export const requestColumns = [
  "request_id",
  "created_at",
  "team_id",
  "key_id",
  "provider",
  "model",
  "alias",
  "endpoint",
  "stream",
  "status_code",
  "outcome",
  "cost_status",
  "duration_ms",
  "ttfb_ms",
  "attempt",
  "fallback_from",
  "prompt_tokens",
  "completion_tokens",
  "cost_usd",
  "saved_usd",
  "redaction_count",
];
export const auditColumns = [
  "id",
  "occurred_at",
  "actor",
  "action",
  "target_type",
  "target_id",
  "details",
];
export function csvStream(
  first: Page<Record<string, unknown>>,
  columns: string[],
  base: string,
  key: string,
  path: string,
  query: URLSearchParams,
) {
  const encoder = new TextEncoder();
  let page = first;
  let sent = 0;
  let header = false;
  const seen = new Set<string>();
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        if (!header) {
          controller.enqueue(encoder.encode(csvRow(columns)));
          header = true;
        }
        const rows = (browserResponse(page.data, false) as Record<string, unknown>[]).slice(
          0,
          EXPORT_CAP - sent,
        );
        controller.enqueue(
          encoder.encode(rows.map((row) => csvRow(columns.map((column) => row[column]))).join("")),
        );
        sent += rows.length;
        if (sent >= EXPORT_CAP || page.next_cursor == null) {
          controller.close();
          return;
        }
        const cursor = String(page.next_cursor);
        if (seen.has(cursor)) throw new Error("Repeated cursor");
        seen.add(cursor);
        query.set("cursor", cursor);
        page = await adminRequest(base, key, `${path}?${query}`);
      } catch {
        controller.error(new Error("Export could not be completed. Please retry."));
      }
    },
  });
}
