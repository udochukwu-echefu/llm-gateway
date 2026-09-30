import type { Catalog } from "./policy-contracts";

// Older gateways omit the complete valid-region list. Keep their valid regions even
// when no reviewed model runs there, and pick up any region advertised by a model.
export const fallbackRegions = ["us", "eu", "cn", "global", "unknown"] as const;

export function catalogRegions(catalog?: Catalog): string[] {
  if (catalog?.regions !== undefined) return [...new Set(catalog.regions)];
  return [
    ...new Set([...fallbackRegions, ...(catalog?.models ?? []).map((model) => model.region)]),
  ];
}
