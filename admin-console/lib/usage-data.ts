import type { Budget, NamedResource, Page, Usage } from "./contracts";
import { browserApi } from "./browser-api";
export async function allPages<T>(path: string): Promise<T[]> {
  const result: T[] = [];
  let cursor: string | number | null = null;
  do {
    const page: Page<T> = await browserApi(
      `${path}${path.includes("?") ? "&" : "?"}page_size=500${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    );
    result.push(...page.data);
    cursor = page.next_cursor;
  } while (cursor !== null);
  return result;
}
export function currentMonth(now = new Date()) {
  return {
    since: `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-01`,
    until: new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 0))
      .toISOString()
      .slice(0, 10),
  };
}
export async function loadUsage(org: string) {
  const base = `/api/admin/orgs/${encodeURIComponent(org)}`;
  const month = new URLSearchParams(currentMonth());
  const [teams, byTeam, byModel, byDay] = await Promise.all([
    allPages<NamedResource>(`${base}/teams`),
    allPages<Usage>(`${base}/usage?${month}&group_by=team`),
    allPages<Usage>(`${base}/usage?${month}&group_by=model`),
    allPages<Usage>(`${base}/usage?${month}&group_by=day`),
  ]);
  const budgets = await Promise.all(
    teams.map(async (team) => ({
      team,
      budget: await browserApi<Budget>(`${base}/teams/${encodeURIComponent(team.name)}/budget`),
    })),
  );
  return { budgets, byTeam, byModel, byDay };
}
