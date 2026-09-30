"use client";
import type { Budget, Usage } from "@/lib/contracts";
import { currentMonth, allPages } from "@/lib/usage-data";
import { useEffect, useState } from "react";
import { money, pico, budgetPercent } from "@/lib/money";
import { useResource } from "./use-resource";
import { DataState } from "./data-state";
import { MutationForm } from "./mutation-form";
export function TeamBudget({ base, orgBase, team }: {
  base: string;
  orgBase: string;
  team: string;
}) {
  const budget = useResource<Budget>(`/api/admin${base}/budget`);
  const [usage, setUsage] = useState<Usage[]>();
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true; allPages<Usage>(`/api/admin${orgBase}/usage?group_by=team&${new URLSearchParams(currentMonth())}`).then((data) => {
      if (active)
        setUsage(data);
    }).catch((e: Error) => {
      if (active)
        setError(e.message);
    }); return () => { active = false; };
  }, [orgBase]);
  const row = usage?.find((r) => r.group === team);
  const spend = row ? row.cost_usd : "0";
  return <section className="panel">
    <h2>Monthly budget</h2>
    <DataState {...budget} />
    <DataState loading={!usage && !error} error={error} />
    {budget.data && usage && <>
      <div className="budget-summary">
        <p className="eyebrow">PRICED SPEND · CURRENT UTC MONTH</p>
        <p className="spend">{money(spend)} <span className="muted">/ {pico(budget.data.effective.usd) === 0n ? "Unlimited" : money(budget.data.effective.usd)}</span>
        </p>
        <progress max="100" value={spend && spend !== "None" ? budgetPercent(spend, budget.data.effective.usd) : 0} aria-label="Monthly budget used" />
        <p>Alert threshold: {budget.data.effective.alert_at} of budget · {budget.data.overrides.usd === null ? "Default" : "Override"}</p>{row && (row.usage_missing + row.stream_incomplete > 0 || spend === null || spend === "None") && <p className="warning">Unpriced usage: {row.usage_missing + row.stream_incomplete} requests. Actual spend is not fully known.</p>}</div>
      <MutationForm key={JSON.stringify(budget.data.overrides)} path={`${base}/budget`} method="PUT" label="Save budget" fields={[{ name: "usd", label: "Monthly budget (USD)", type: "decimal", value: budget.data.effective.usd, hint: "0 means unlimited. Use a decimal string, up to 12 places." }, { name: "alert_at", label: "Alert threshold (0–1)", type: "decimal", value: budget.data.effective.alert_at }]} onSuccess={() => { budget.refresh(); setNotice("Budget saved."); }} />
    </>}
    <p role="status">{notice}</p>
  </section>;
}
