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
  let decimals = 2;
  if (amount > 0n && amount < SCALE / 100n) {
    const first = 12 - amount.toString().length;
    decimals = Math.min(12, first + 4);
  }
  const divisor = 10n ** BigInt(12 - decimals);
  let rounded = (amount + divisor / 2n) / divisor;
  if (decimals > 2 && rounded.toString().length > 4) {
    rounded /= 10n;
    decimals--;
  }
  const unit = 10n ** BigInt(decimals);
  const fraction = (rounded % unit).toString().padStart(decimals, "0");
  return `$${(rounded / unit).toLocaleString("en-US")}.${fraction}`;
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
