import { formatCount } from "@/lib/number-format";
import { SortableTable } from "./sortable-table";
import type { Usage } from "@/lib/contracts";
import { dailyTokens } from "@/lib/usage-trend";
import { UsageChart } from "./usage-chart";

export function DailyUsage({ rows }: { rows: Usage[] }) {
  const days = rows.map((row) => row.group);
  return (
    <>
      <p className="muted">Legend: ● Requests · ■ Total tokens. Unknown token totals leave gaps.</p>
      <UsageChart
        title="Daily requests"
        unit="Requests"
        days={days}
        values={rows.map((row) => row.requests)}
        marker="circle"
      />
      <UsageChart
        title="Daily total tokens"
        unit="Tokens"
        days={days}
        values={rows.map(dailyTokens)}
        marker="square"
      />
      <SortableTable name="daily-usage-1" className="daily-usage-table">
        <caption>Daily values in UTC; the text alternative to both charts</caption>
        <thead>
          <tr>
            <th>Day</th>
            <th>Requests</th>
            <th>Input tokens</th>
            <th>Output tokens</th>
            <th>Total tokens</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.group}>
              <td>{row.group}</td>
              <td>{formatCount(row.requests)}</td>
              <td>{formatCount(row.prompt_tokens)}</td>
              <td>{formatCount(row.completion_tokens)}</td>
              <td>{formatCount(dailyTokens(row))}</td>
            </tr>
          ))}
        </tbody>
      </SortableTable>
    </>
  );
}
