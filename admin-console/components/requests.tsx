"use client";
import { useState } from "react";
import { useListQuery } from "./use-list-query";
import { OrgScope, useOrgScope } from "./org-scope";
import { FilterBar, SortHeading, PageCount, type FilterField } from "./list-controls";
import { usePagedResource } from "./use-paged-resource";
import { DataState } from "./data-state";
import { RecordTime } from "./record-time";
import { MoneyValue } from "./money-value";
import { RequestDetail } from "./request-detail";
import { listSort } from "@/lib/list-query";
import type { RequestAttempt } from "@/lib/console-contracts";
const fields: FilterField[] = [
  { name: "since", label: "From timestamp (UTC)", type: "datetime" },
  { name: "until", label: "To timestamp (UTC)", type: "datetime" },
  { name: "team", label: "Team" },
  { name: "key_id", label: "Key ID" },
  {
    name: "provider",
    label: "Provider",
    options: ["groq", "deepseek", "gemini", "openai", "zai", "nvidia"],
  },
  { name: "model", label: "Model" },
  { name: "alias", label: "Alias" },
  { name: "endpoint", label: "Endpoint", options: ["chat", "embeddings"] },
  { name: "status", label: "Status (e.g. 5xx or 502)" },
  {
    name: "outcome",
    label: "Outcome",
    options: [
      "success",
      "upstream_error",
      "client_disconnected",
      "stream_error",
      "gateway_error",
      "cache_hit",
    ],
  },
  {
    name: "cost_status",
    label: "Cost status",
    options: ["priced", "unpriced", "usage_missing", "stream_incomplete", "not_billed", "cached"],
  },
  ...["stream", "cache_hit", "redacted", "fallback", "retried"].map((name) => ({
    name,
    label: name.replace("_", " "),
    options: ["true", "false"],
  })),
  { name: "min_latency", label: "Minimum latency (ms)", type: "number" },
];
export function Requests() {
  const scope = useOrgScope();
  const { params, set } = useListQuery();
  const [detail, setDetail] = useState<string>();
  const query = new URLSearchParams(
    Array.from(params).filter(([key]) => fields.some((field) => field.name === key)),
  );
  query.set("page_size", "50");
  return (
    <>
      <h1>Requests</h1>
      <p className="muted">Prompts and responses are never stored. This log is metadata only.</p>
      <OrgScope {...scope} />
      <div className="quick-ranges" aria-label="Quick ranges">
        {[
          ["15m", 15 / 60],
          ["1h", 1],
          ["24h", 24],
          ["7d", 168],
          ["30d", 720],
        ].map(([label, hours]) => (
          <button
            key={label}
            className="secondary"
            onClick={() =>
              set({
                since: new Date(Date.now() - Number(hours) * 3600000).toISOString(),
                until: new Date().toISOString(),
              })
            }
          >
            {label}
          </button>
        ))}
        <span>Custom: use the timestamp fields</span>
      </div>
      <section className="panel">
        <details>
          <summary>Request filters</summary>
          <FilterBar fields={fields} />
        </details>
      </section>
      {scope.org && (
        <RequestList
          key={scope.org}
          org={scope.org}
          query={query.toString()}
          params={params}
          detail={detail}
          setDetail={setDetail}
        />
      )}
    </>
  );
}
function RequestList({
  org,
  query,
  params,
  detail,
  setDetail,
}: {
  org: string;
  query: string;
  params: URLSearchParams | Pick<URLSearchParams, "get">;
  detail?: string;
  setDetail: (value: string | undefined) => void;
}) {
  const resource = usePagedResource<RequestAttempt>(
    `/api/admin/orgs/${encodeURIComponent(org)}/requests?${query}`,
  );
  const sort = (params.get("sort") ?? "created_at") as keyof RequestAttempt;
  const rows = listSort(resource.data, sort, params.get("direction") ?? "desc");
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>Recorded attempts</h2>
        <a
          className="button secondary"
          href={`/api/export/requests?org=${encodeURIComponent(org)}&${query}`}
        >
          Export CSV (up to 10,000 attempts)
        </a>
      </div>
      <p className="muted">
        Columns sort the loaded attempts. Load more to include earlier records.
      </p>
      <DataState {...resource} />
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <SortHeading field="created_at">Time</SortHeading>
              <SortHeading field="request_id">Request ID</SortHeading>
              <SortHeading field="provider">Provider / model</SortHeading>
              <SortHeading field="status_code">Status</SortHeading>
              <SortHeading field="duration_ms">Duration</SortHeading>
              <SortHeading field="cost_usd">Cost</SortHeading>
              <SortHeading field="outcome">Outcome</SortHeading>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <RecordTime value={row.created_at} />
                </td>
                <td>
                  <button className="secondary" onClick={() => setDetail(row.request_id)}>
                    {row.request_id}
                  </button>
                  <small>Attempt {row.attempt}</small>
                </td>
                <td>
                  {row.provider}
                  <small>{row.model}</small>
                </td>
                <td>
                  <span className={row.status_code >= 400 ? "badge danger" : "badge"}>
                    {row.status_code}
                  </span>
                </td>
                <td>{row.duration_ms ?? "Unknown"} ms</td>
                <td>
                  <MoneyValue value={row.cost_usd} />
                  <small>{row.cost_status}</small>
                </td>
                <td>
                  {row.outcome}
                  {row.fallback_from && <small>Fallback</small>}
                  {row.attempt > 1 && <small>Retry</small>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!resource.loading && !rows.length && (
        <p className="empty">
          No request results match this filter. Clear filters or widen the range.
        </p>
      )}
      <PageCount
        shown={rows.length}
        total={resource.total}
        more={!!resource.cursor}
        onMore={resource.more}
      />
      {detail && <RequestDetail org={org} id={detail} onClose={() => setDetail(undefined)} />}
    </section>
  );
}
