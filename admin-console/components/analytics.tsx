"use client";
import { Select } from "./select";
import { useState } from "react";
import { OrgScope, useOrgScope } from "./org-scope";
import { useListQuery } from "./use-list-query";
import { useResource } from "./use-resource";
import { FilterBar, SortHeading, PageCount } from "./list-controls";
import { DataState } from "./data-state";
import { MoneyValue } from "./money-value";
import { formatMeasure } from "@/lib/number-format";
import { AnalyticsChart } from "./analytics-chart";
import { listSort } from "@/lib/list-query";
import type { AnalyticsRow } from "@/lib/console-contracts";
import { GooeyRanges } from "./gooey-ranges";
export function Analytics() {
  const scope = useOrgScope();
  const { params, set } = useListQuery();
  return (
    <>
      <div className="screen-heading">
        <h1>Analytics</h1>
        <p>
          Performance and reliability over recorded attempts, including retries and fallbacks. These
          percentiles do not measure gateway overhead.
        </p>
      </div>
      <OrgScope {...scope} />
      <div className="quick-ranges">
        <GooeyRanges
          items={[7, 30, 90].map((days) => ({
            label: `${days} days`,
            value: days,
            duration: days * 86400000,
          }))}
          since={params.get("since")}
          until={params.get("until")}
          onSelect={(days) =>
            set({
              since: new Date(Date.now() - days * 86400000).toISOString(),
              until: new Date().toISOString(),
            })
          }
        />
      </div>
      <section className="panel">
        <FilterBar
          fields={[
            { name: "since", label: "From timestamp (UTC)", type: "datetime" },
            { name: "until", label: "To timestamp (UTC)", type: "datetime" },
            { name: "group_by", label: "Group by", options: ["provider", "model", "team"] },
            { name: "bucket", label: "Time bucket", options: ["hour", "day"] },
          ]}
        />
      </section>
      {scope.org && (
        <AnalyticsData
          org={scope.org}
          query={new URLSearchParams(
            Array.from(params).filter(([key]) =>
              ["since", "until", "group_by", "bucket"].includes(key),
            ),
          ).toString()}
        />
      )}
    </>
  );
}
function AnalyticsData({ org, query }: { org: string; query: string }) {
  const resource = useResource<{ data: AnalyticsRow[] }>(
    `/api/admin/orgs/${encodeURIComponent(org)}/analytics?${query}`,
  );
  const { params, set } = useListQuery();
  const [measure, setMeasure] = useState<
    "duration_p95" | "ttfb_p95" | "requests" | "error_rate" | "cache_hit_rate"
  >("duration_p95");
  const rows = listSort(
    resource.data?.data ?? [],
    (params.get("sort") ?? "bucket") as keyof AnalyticsRow,
    params.get("direction") ?? "asc",
  );
  const limit = Number(params.get("shown") ?? 50);
  return (
    <section className="panel analytics-panel">
      <DataState {...resource} />
      {resource.data && (
        <>
          <label>
            Chart measure
            <Select
              aria-label="Chart measure"
              value={measure}
              onValueChange={(next) => setMeasure(next as typeof measure)}
            >
              {["duration_p95", "ttfb_p95", "requests", "error_rate", "cache_hit_rate"].map(
                (value) => (
                  <option key={value}>{value}</option>
                ),
              )}
            </Select>
          </label>
          <AnalyticsChart
            rows={resource.data.data}
            measure={measure}
            bucket={params.get("bucket") === "hour" ? "hour" : "day"}
          />
          <div
            className="table-scroll analytics-table-scroll"
            tabIndex={0}
            role="region"
            aria-label="Analytics results table"
          >
            <table className="analytics-table">
              <caption>UTC buckets; durations in ms or seconds; rates as percentages.</caption>
              <thead>
                <tr>
                  {[
                    "bucket",
                    "group",
                    "requests",
                    "error_rate",
                    "duration_p50",
                    "duration_p95",
                    "duration_p99",
                    "ttfb_p50",
                    "ttfb_p95",
                    "ttfb_p99",
                    "fallback_count",
                    "retry_count",
                    "cache_hit_rate",
                    "saved_usd",
                    "redaction_count",
                  ].map((field) => (
                    <SortHeading key={field} field={field}>
                      {field.replaceAll("_", " ")}
                    </SortHeading>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, limit).map((row, index) => (
                  <tr key={index}>
                    {[
                      "bucket",
                      "group",
                      "requests",
                      "error_rate",
                      "duration_p50",
                      "duration_p95",
                      "duration_p99",
                      "ttfb_p50",
                      "ttfb_p95",
                      "ttfb_p99",
                      "fallback_count",
                      "retry_count",
                      "cache_hit_rate",
                      "saved_usd",
                      "redaction_count",
                    ].map((field) => (
                      <td key={field}>
                        {field === "saved_usd" ? (
                          <MoneyValue value={row.saved_usd} />
                        ) : ["bucket", "group"].includes(field) ? (
                          (row[field as keyof AnalyticsRow] ?? "Unknown")
                        ) : (
                          formatMeasure(field, row[field as keyof AnalyticsRow])
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!rows.length && <p className="empty">No recorded attempts in this range.</p>}
          <PageCount
            shown={Math.min(limit, rows.length)}
            total={rows.length}
            more={limit < rows.length}
            onMore={() => set({ shown: String(limit + 50) })}
          />
        </>
      )}
    </section>
  );
}
