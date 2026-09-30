import type { AuditEvent, KeyRecord, NamedResource } from "./contracts";
import { allPages, loadUsage } from "./usage-data";
import { summarize, combineGroups } from "./overview-totals";
import { pico, compareMoney } from "./money";
export async function loadOverview() {
  // The API returns all orgs for platform keys and only the caller's org for org keys.
  const [orgs, events] = await Promise.all([
    allPages<NamedResource>("/api/admin/orgs"),
    allPages<AuditEvent>("/api/admin/audit"),
  ]);
  const organizations = await Promise.all(
    orgs.map(async (org) => {
      const [usage, keys] = await Promise.all([
        loadUsage(org.name),
        allPages<KeyRecord>(`/api/admin/orgs/${encodeURIComponent(org.name)}/keys`),
      ]);
      return { org, ...usage, keys };
    }),
  );
  const budgets = organizations.flatMap((o) =>
    o.budgets.map(({ team, budget }) => ({
      org: o.org,
      team,
      budget,
      usage: o.byTeam.find((row) => row.group === team.name),
    })),
  );
  const teamRows = organizations.flatMap((o) => o.byTeam);
  const closest = budgets
    .filter((b) => pico(b.budget.effective.usd) > 0n)
    .sort((a, b) => {
      const left = pico(a.usage?.cost_usd ?? "0") * pico(b.budget.effective.usd);
      const right = pico(b.usage?.cost_usd ?? "0") * pico(a.budget.effective.usd);
      return left === right ? 0 : left > right ? -1 : 1;
    })
    .slice(0, 5);
  return {
    organizations,
    summary: summarize(
      teamRows,
      organizations.flatMap((o) => o.keys),
      budgets.length,
    ),
    byDay: combineGroups(organizations.flatMap((o) => o.byDay)),
    models: combineGroups(organizations.flatMap((o) => o.byModel))
      .sort((a, b) => compareMoney(a.cost_usd, b.cost_usd))
      .slice(0, 5),
    closest,
    recent: events.sort((a, b) => b.id - a.id).slice(0, 5),
  };
}
