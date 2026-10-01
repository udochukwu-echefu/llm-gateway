"use client";
import { formatDuration, formatCount } from "@/lib/number-format";
import { useResource } from "./use-resource";
import { DataState } from "./data-state";
import { Dialog } from "./dialog";
import { CopyId } from "./copy-id";
import { RecordTime } from "./record-time";
import { MoneyValue } from "./money-value";
import type { RequestAttempt } from "@/lib/console-contracts";
export function RequestDetail({
  org,
  id,
  onClose,
}: {
  org: string;
  id: string;
  onClose: () => void;
}) {
  const detail = useResource<{ data: RequestAttempt[] }>(
    `/api/admin/orgs/${encodeURIComponent(org)}/requests/${encodeURIComponent(id)}`,
  );
  return (
    <Dialog drawer title="Request attempt timeline" onClose={onClose}>
      <CopyId value={id} />
      <p>Prompts and responses are never stored. This log is metadata only.</p>
      <DataState {...detail} />
      <ol className="attempt-timeline">
        {detail.data?.data.map((row) => (
          <li key={row.id}>
            <h3>
              Attempt {row.attempt}: {row.provider} {row.status_code}
            </h3>
            <p>
              {row.fallback_from
                ? `Fallback from ${row.fallback_from}`
                : row.attempt > 1
                  ? "Retry"
                  : "First attempt"}{" "}
              · {row.outcome}
            </p>
            <RecordTime value={row.created_at} />
            <dl>
              <dt>Model</dt>
              <dd>{row.model}</dd>
              <dt>Duration / first byte</dt>
              <dd>
                {formatDuration(row.duration_ms)} / {formatDuration(row.ttfb_ms)}
              </dd>
              <dt>Cost</dt>
              <dd>
                <MoneyValue value={row.cost_usd} /> · {row.cost_status}
              </dd>
              <dt>Tokens (input / output)</dt>
              <dd>
                {formatCount(row.prompt_tokens)} / {formatCount(row.completion_tokens)}
              </dd>
              <dt>Redactions</dt>
              <dd>{row.redaction_count ?? "Unknown"}</dd>
              <dt>Key ID</dt>
              <dd>
                <CopyId value={row.key_id} />
              </dd>
            </dl>
          </li>
        ))}
      </ol>
      <button className="secondary" onClick={onClose}>
        Close
      </button>
    </Dialog>
  );
}
