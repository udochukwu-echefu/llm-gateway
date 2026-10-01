import { formatCount } from "@/lib/number-format";
import { money } from "@/lib/money";
import type { summarize } from "@/lib/overview-totals";
export function OverviewCards({ summary }: { summary: ReturnType<typeof summarize> }) {
  const cards = [
    [
      "spend",
      "Priced spend this month",
      money(summary.spend),
      `${formatCount(summary.unpriced)} unpriced requests`,
    ],
    ["requests", "Requests", formatCount(summary.requests), "Provider attempts and cache hits"],
    [
      "tokens",
      "Known tokens",
      formatCount(summary.tokens),
      summary.incompleteTokens ? "Partial total · some usage is unknown" : "Input + output",
    ],
    [
      "savings",
      "Cache savings",
      money(summary.savings),
      summary.unknownSavings ? "Some savings are unpriced" : "Estimated savings at reviewed prices",
    ],
    ["keys", "Active keys", formatCount(summary.activeKeys), "Not revoked or expired"],
    ["teams", "Teams", formatCount(summary.teams), "Across visible organisations"],
  ];
  return (
    <dl className="overview-cards">
      {cards.map(([id, label, value, note]) => (
        <div className="summary-card" key={id}>
          <dt>{label}</dt>
          <dd
            title={
              id === "spend"
                ? (summary.spend ?? "Unknown")
                : id === "savings"
                  ? (summary.savings ?? "Unknown")
                  : undefined
            }
            data-testid={`summary-${id}`}
          >
            {value}
          </dd>
          <p className="muted">{note}</p>
        </div>
      ))}
    </dl>
  );
}
