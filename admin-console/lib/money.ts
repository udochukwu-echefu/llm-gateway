const SCALE = 10n ** 12n;
export function pico(value: string): bigint {
  const match = /^(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d{1,2}))?$/.exec(value);
  if (!match || value.length > 64) throw new Error("Invalid decimal money");
  const digits = BigInt(match[1] + (match[2] ?? ""));
  const shift = 12 + Number(match[3] ?? "0") - (match[2]?.length ?? 0);
  if (Math.abs(shift) > 30) throw new Error("Invalid decimal precision");
  if (shift >= 0) return digits * 10n ** BigInt(shift);
  const divisor = 10n ** BigInt(-shift);
  if (digits % divisor !== 0n) throw new Error("Invalid decimal precision");
  return digits / divisor;
}
export function money(value: string | null): string {
  if (value === null) return "Unpriced";
  const amount = pico(value);
  const fraction = (amount % SCALE).toString().padStart(12, "0").replace(/0+$/, "").padEnd(2, "0");
  return `$${(amount / SCALE).toLocaleString("en-US")}.${fraction}`;
}
export function budgetPercent(spend: string, budget: string): number {
  const cap = pico(budget);
  if (cap === 0n) return 0;
  const percentage = (pico(spend) * 100n) / cap;
  return Number(percentage > 100n ? 100n : percentage);
}
export function compareMoney(a: string | null, b: string | null) {
  const left = pico(a ?? "0");
  const right = pico(b ?? "0");
  return left === right ? 0 : left > right ? -1 : 1;
}
