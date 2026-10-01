import { money } from "@/lib/money";
export function MoneyValue({ value }: { value: string | null }) {
  return (
    <span title={value === null ? "Unknown cost" : `$${value} exact USD`}>{money(value)}</span>
  );
}
