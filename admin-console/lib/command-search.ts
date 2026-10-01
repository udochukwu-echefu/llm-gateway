import type { SearchResult } from "./console-contracts";
import type { Identity } from "./contracts";
export function scopedResults(results: SearchResult[], identity: Identity) {
  return results.filter(
    (item) => !identity.organization || item.org === identity.organization.name,
  );
}
export function resultUrl(item: SearchResult) {
  const base = `/orgs/${encodeURIComponent(item.org)}`;
  return item.kind === "org"
    ? base
    : item.kind === "team"
      ? `${base}/teams/${encodeURIComponent(item.team!)}`
      : `/keys?org=${encodeURIComponent(item.org)}&q=${encodeURIComponent(item.id)}`;
}
export const commandPages = [
  "Overview",
  "Organisations",
  "Requests",
  "Analytics",
  "Keys",
  "Models",
  "Audit",
  "Settings",
];
