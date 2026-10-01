import { money } from "@/lib/money";
import type { summarize } from "@/lib/overview-totals";
export function OverviewCards({ summary }: { summary: ReturnType<typeof summarize> }) {
  const cards = [
    [
      "spend",
      "Priced spend this month",
      money(summary.spend),
      `${summary.unpriced.toLocaleString("en-US")} unpriced requests`,
    ],
    [
      "requests",
      "Requests",
      summary.requests.toLocaleString("en-US"),
      "Provider attempts and cache hits",
    ],
    [
      "tokens",
      "Known tokens",
      summary.tokens.toLocaleString("en-US"),
      summary.incompleteTokens ? "Partial total · some usage is unknown" : "Input + output",
    ],
    [
      "savings",
      "Cache savings",
      money(summary.savings),
      summary.unknownSavings ? "Some savings are unpriced" : "Estimated savings at reviewed prices",
    ],
    ["keys", "Active keys", summary.activeKeys.toLocaleString("en-US"), "Not revoked or expired"],
    ["teams", "Teams", summary.teams.toLocaleString("en-US"), "Across visible organisations"],
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
