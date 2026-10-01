import { MoneyValue } from "./money-value";
import { SortableTable } from "./sortable-table";
import Link from "next/link";
import type { loadOverview } from "@/lib/overview-data";
import { budgetPercent, pico } from "@/lib/money";
export function OverviewBudgets({
  rows,
}: {
  rows: Awaited<ReturnType<typeof loadOverview>>["closest"];
}) {
  return (
    <section className="panel">
      <h2>Teams closest to their budget</h2>
      {rows.length ? (
        <SortableTable name="overview-budgets-1">
          <thead>
            <tr>
              <th>Team / organisation</th>
              <th>Priced spend / budget</th>
              <th>Alert threshold</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ org, team, budget, usage }) => {
              const spend = usage?.cost_usd ?? (usage ? null : "0");
              const threshold = pico(budget.effective.alert_at);
              const reached =
                spend !== null &&
                pico(spend) * 10n ** 12n >= pico(budget.effective.usd) * threshold;
              const over =
                spend !== null &&
                pico(budget.effective.usd) > 0n &&
                pico(spend) >= pico(budget.effective.usd);
              return (
                <tr key={team.id}>
                  <td>
                    <Link
                      prefetch={false}
                      href={`/orgs/${encodeURIComponent(org.name)}/teams/${encodeURIComponent(team.name)}`}
                    >
                      {team.name}
                    </Link>
                    <small>{org.name}</small>
                  </td>
                  <td>
                    <span
                      title={`Exact spend: ${spend ?? "unknown"}; budget: ${budget.effective.usd}`}
                    >
                      <MoneyValue value={spend} /> /{" "}
                      <span title={`Exact budget: ${budget.effective.usd}`}>
                        ${budget.display_usd ?? budget.effective.usd}
                      </span>
                    </span>
                    <progress
                      className={over ? "danger" : reached ? "warning" : ""}
                      max="100"
                      aria-label={`${team.name} budget used`}
                      value={spend === null ? 0 : budgetPercent(spend, budget.effective.usd)}
                    />
                    {(usage?.usage_missing ?? 0) + (usage?.stream_incomplete ?? 0) > 0 && (
                      <small className="warning">Plus unpriced usage</small>
                    )}
                  </td>
                  <td>
                    <span className={over ? "badge danger" : reached ? "badge warning" : "badge"}>
                      {spend === null
                        ? "Unknown spend"
                        : over
                          ? "Over budget · Requests are being refused"
                          : reached
                            ? "Above alert threshold"
                            : "Below alert threshold"}{" "}
                      · {Number((threshold * 100n) / 10n ** 12n)}%
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </SortableTable>
      ) : (
        <p className="empty">No team budgets yet. Set a monthly budget on a team’s Budget tab.</p>
      )}
    </section>
  );
}
