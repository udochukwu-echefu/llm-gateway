"use client";
import { formatDuration, formatRate, formatCount } from "@/lib/number-format";
import { useResource } from "./use-resource";
import { useListQuery } from "./use-list-query";
import { SortHeading, PageCount } from "./list-controls";
import { DataState } from "./data-state";
import { listSort } from "@/lib/list-query";
interface Provider {
  provider: string;
  enabled: boolean;
  host: string;
  circuit_breaker: string | null;
  "15m": { attempts: number; error_rate: string | number | null; p95_ms: number | null };
  "24h": { attempts: number; error_rate: string | number | null; p95_ms: number | null };
}
export function Providers() {
  const resource = useResource<{ data: Provider[] }>("/api/admin/providers");
  const { params } = useListQuery();
  const rows = listSort(
    resource.data?.data ?? [],
    (params.get("sort") ?? "provider") as keyof Provider,
    params.get("direction") ?? "asc",
  );
  return (
    <>
      <h1>Providers</h1>
      <p>
        Circuit breaker state is local to <strong>this replica</strong> serving the admin API.
        Recorded health includes all organisations.
      </p>
      <section className="panel">
        <DataState {...resource} />
        <table>
          <thead>
            <tr>
              <SortHeading field="provider">Provider</SortHeading>
              <SortHeading field="enabled">Enabled</SortHeading>
              <SortHeading field="host">Host</SortHeading>
              <SortHeading field="circuit_breaker">Breaker · this replica</SortHeading>
              <th>15 minutes: attempts / error rate / p95 latency</th>
              <th>24 hours: attempts / error rate / p95 latency</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.provider}>
                <td>{row.provider}</td>
                <td>{row.enabled ? "Yes" : "No"}</td>
                <td>{row.host}</td>
                <td>{row.circuit_breaker ?? "Not configured"}</td>
                {["15m", "24h"].map((window) => (
                  <td key={window}>
                    {formatCount(row[window as "15m"].attempts)} /{" "}
                    {formatRate(row[window as "15m"].error_rate)} /{" "}
                    {formatDuration(row[window as "15m"].p95_ms)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <PageCount shown={rows.length} total={rows.length} />
      </section>
    </>
  );
}
