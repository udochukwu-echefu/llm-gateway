"use client";
import Link from "next/link";
import { usePagedResource } from "./use-paged-resource";
import { useListQuery } from "./use-list-query";
import { SortHeading, PageCount } from "./list-controls";
import { RecordTime } from "./record-time";
import { MoneyValue } from "./money-value";
import { CopyId } from "./copy-id";
import { DataState } from "./data-state";
import { listSort } from "@/lib/list-query";
import { pico } from "@/lib/money";
interface Team {
  id: string;
  name: string;
  created_at: string;
  spend_usd: string | null;
  budget_usd: string;
  key_count: number;
  last_activity: string | null;
  budget_percent: number | null;
}
export function TeamsInventory({ base }: { base: string }) {
  const resource = usePagedResource<Team>(`/api/admin${base}/teams?page_size=25`);
  const { params } = useListQuery();
  const rows = listSort(
    resource.data.map((row) => ({
      ...row,
      budget_percent:
        row.spend_usd == null || pico(row.budget_usd) === 0n
          ? null
          : Number((pico(row.spend_usd) * 100n) / pico(row.budget_usd)),
    })),
    (params.get("sort") ?? "name") as keyof Team,
    params.get("direction") ?? "asc",
  );
  return (
    <>
      <DataState {...resource} />
      <table>
        <thead>
          <tr>
            <SortHeading field="name">Team</SortHeading>
            <SortHeading field="spend_usd">Spend this month (UTC)</SortHeading>
            <SortHeading field="budget_percent">Budget use</SortHeading>
            <SortHeading field="key_count">Keys</SortHeading>
            <SortHeading field="last_activity">Last activity</SortHeading>
            <SortHeading field="created_at">Created</SortHeading>
            <SortHeading field="id">Team ID</SortHeading>
          </tr>
        </thead>
        <tbody>
          {rows.map((team) => (
            <tr key={team.id}>
              <td>
                <Link prefetch={false} href={`${base}/teams/${encodeURIComponent(team.name)}`}>
                  {team.name}
                </Link>
              </td>
              <td>
                <MoneyValue value={team.spend_usd} />
              </td>
              <td>
                {pico(team.budget_usd) === 0n
                  ? "Unlimited"
                  : team.budget_percent == null
                    ? "Unknown"
                    : `${team.budget_percent}%`}
              </td>
              <td>{team.key_count}</td>
              <td>
                <RecordTime value={team.last_activity} />
              </td>
              <td>
                <RecordTime value={team.created_at} />
              </td>
              <td>
                <CopyId value={team.id} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!resource.loading && !rows.length && (
        <p className="empty">
          Create your first team using the form above. A team groups application keys, policies and
          budgets.
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
