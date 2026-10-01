import { pico } from "./money";
export function budgetState(spend: string | null, budget: string, threshold: string) {
  if (spend === null) return "unknown";
  if (pico(budget) === 0n) return "unlimited";
  if (pico(spend) >= pico(budget)) return "over";
  return pico(spend) * 10n ** 12n >= pico(budget) * pico(threshold) ? "warning" : "under";
}
export const budgetLabels = {
  unknown: "Unknown spend",
  unlimited: "Unlimited",
  over: "Over budget · Requests are being refused",
  warning: "Above alert threshold",
  under: "Below alert threshold",
};
