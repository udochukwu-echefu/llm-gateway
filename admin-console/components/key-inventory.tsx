"use client";
import { useEffect, useState } from "react";
import { useListQuery } from "./use-list-query";
import { usePagedResource } from "./use-paged-resource";
import { FilterBar, SortHeading, PageCount } from "./list-controls";
import { DataState } from "./data-state";
import { RecordTime } from "./record-time";
import { CopyId } from "./copy-id";
import { listSort } from "@/lib/list-query";
import type { ConsoleKey } from "@/lib/console-contracts";
export function KeyInventory({
  orgBase,
  team,
  onRevoke,
}: {
  orgBase: string;
  team?: string;
  onRevoke?: (id: string) => void;
}) {
  const { params } = useListQuery();
  const [now, setNow] = useState(0);
  useEffect(() => {
    queueMicrotask(() => setNow(Date.now()));
  }, []);
  const query = new URLSearchParams(
    Array.from(params).filter(([key]) => ["q", "status", "team"].includes(key)),
  );
  if (team) query.set("team", team);
  query.set("page_size", "25");
  const resource = usePagedResource<ConsoleKey>(`/api/admin${orgBase}/keys?${query}`);
  const rows = listSort(
    resource.data.map((key) => ({
      ...key,
      status: key.revoked_at
        ? "Revoked"
        : key.expires_at && Date.parse(key.expires_at) <= now
          ? "Expired"
          : key.expires_at && Date.parse(key.expires_at) <= now + 7 * 86400000
            ? "Expiring soon"
            : "Active",
    })),
    (params.get("sort") ?? "name") as keyof (ConsoleKey & { status: string }),
    params.get("direction") ?? "asc",
  );
  return (
    <>
      <FilterBar
        fields={[
          { name: "q", label: "Search by name or key ID" },
          {
            name: "status",
            label: "Key status",
            options: ["active", "expiring", "expired", "revoked", "never-used"],
          },
          ...(team ? [] : [{ name: "team", label: "Team" }]),
        ]}
      />
      <DataState {...resource} />
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <SortHeading field="name">Name / key ID</SortHeading>
              <SortHeading field="status">Status</SortHeading>
              <SortHeading field="team_id">Team ID</SortHeading>
              <SortHeading field="created_at">Created</SortHeading>
              <SortHeading field="expires_at">Expiry</SortHeading>
              <SortHeading field="last_used_at">Last used</SortHeading>
              {onRevoke && <th>Action</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((key) => {
              const expired = key.expires_at && Date.parse(key.expires_at) <= now;
              const soon =
                key.expires_at &&
                Date.parse(key.expires_at) > now &&
                Date.parse(key.expires_at) <= now + 7 * 86400000;
              return (
                <tr key={key.id}>
                  <td>
                    {key.name}
                    <br />
                    <CopyId value={key.key_id} />
                  </td>
                  <td>
                    <span
                      className={
                        key.revoked_at || expired
                          ? "badge danger"
                          : soon
                            ? "badge warning"
                            : "badge"
                      }
                    >
                      {key.revoked_at
                        ? "Revoked"
                        : expired
                          ? "Expired"
                          : soon
                            ? "Expiring soon"
                            : "Active"}
                    </span>
                    {!key.last_used_at && <small>Never used</small>}
                  </td>
                  <td>
                    <CopyId value={key.team_id} />
                  </td>
                  <td>
                    <RecordTime value={key.created_at} />
                  </td>
                  <td>{key.expires_at ? <RecordTime value={key.expires_at} /> : "No expiry"}</td>
                  <td>
                    <RecordTime value={key.last_used_at} />
                  </td>
                  {onRevoke && (
                    <td>
                      <button
                        className="secondary"
                        disabled={!!key.revoked_at}
                        onClick={() => onRevoke(key.key_id)}
                      >
                        Revoke {key.key_id}
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!resource.loading && !rows.length && (
        <p className="empty">
          No keys match this filter. Create your first key on the team’s API keys tab, or clear the
          filter.
        </p>
      )}
      <PageCount
        shown={rows.length}
        total={resource.total}
        more={!!resource.cursor}
        onMore={resource.more}
      />
    </>
  );
}
