"use client";
import { useEffect, useState } from "react";
import { loadUsage, currentMonth } from "@/lib/usage-data";
import { budgetPercent, pico, compareMoney, money } from "@/lib/money";
import { DailyUsage } from "./daily-usage";
import { DataState } from "./data-state";
export function UsageOverview({ org }: {
  org: string;
}) {
  const [data, setData] = useState<Awaited<ReturnType<typeof loadUsage>>>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    let active = true; loadUsage(org).then((result) => {
      if (active)
        setData(result);
    }).catch((e: Error) => {
      if (active)
        setError(e.message);
    }); return () => { active = false; };
  }, [org]);
  return <section className="panel">
    <div className="section-heading">
      <div>
        <p className="eyebrow">CURRENT MONTH · UTC</p>
        <h2>Usage overview</h2>
      </div>
      <span className="badge">{currentMonth().since} — {currentMonth().until}</span>
    </div>
    <DataState loading={!data && !error} error={error} />
    {data && <>
      <h3>Spend by team</h3>{data.budgets.length ? <table>
        <thead>
          <tr>
            <th>Team</th>
            <th>Priced spend / budget</th>
            <th>Unpriced requests</th>
            <th>Cache savings</th>
          </tr>
        </thead>
        <tbody>{data.budgets.map(({ team, budget }) => {
          const row = data.byTeam.find((r) => r.group === team.name); const spend = row ? row.cost_usd : "0"; return <tr key={team.id}>
            <td>{team.name}</td>
            <td>{money(spend)} / {pico(budget.effective.usd) === 0n ? "Unlimited" : money(budget.effective.usd)}<progress aria-label={`${team.name} budget used`} max="100" value={spend !== null ? budgetPercent(spend, budget.effective.usd) : 0} />
            </td>
            <td>{(row?.usage_missing ?? 0) + (row?.stream_incomplete ?? 0)}{row && ((row.usage_missing + row.stream_incomplete) > 0 || spend === null) && <span className="warning"> · Unpriced usage</span>}</td>
            <td>{row ? money(row.saved_usd) : money("0")} · {row?.cache_hits ?? 0} hits</td>
          </tr>;
        })}</tbody>
      </table> : <p className="empty">No teams to report yet.</p>}
      <div className="usage-grid">
        <div>
          <h3>Top models by priced spend</h3>{data.byModel.length ? <table>
            <thead>
              <tr>
                <th>Model</th>
                <th>Requests</th>
                <th>Priced spend</th>
              </tr>
            </thead>
            <tbody>{[...data.byModel].sort((a, b) => compareMoney(a.cost_usd, b.cost_usd)).slice(0, 10).map((r) => <tr key={r.group}>
              <td>{r.group}</td>
              <td>{r.requests}</td>
              <td>{money(r.cost_usd)}{r.usage_missing + r.stream_incomplete > 0 && <span className="warning"> + unpriced</span>}</td>
            </tr>)}</tbody>
          </table> : <p className="empty">No model usage this month.</p>}</div>
        <div>
          <h3>Requests and tokens over time</h3>{data.byDay.length ? <>
            <DailyUsage rows={data.byDay} />
          </> : <p className="empty">No requests this month. Usage appears after receipts are written.</p>}</div>
      </div>
    </>}
  </section>;
}
