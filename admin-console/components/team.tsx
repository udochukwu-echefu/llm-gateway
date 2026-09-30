"use client";
import Link from "next/link";
import { useState } from "react";
import type { Limits } from "@/lib/contracts";
import { useResource } from "./use-resource";
import { DataState } from "./data-state";
import { TeamKeys } from "./team-keys";
import { TeamLimits } from "./team-limits";
import { TeamBudget } from "./team-budget";
export function Team({ org, team }: { org: string; team: string }) {
  const [tab, setTab] = useState("keys");
  const orgBase = `/orgs/${encodeURIComponent(org)}`;
  const base = `${orgBase}/teams/${encodeURIComponent(team)}`;
  const exists = useResource<Limits>(`/api/admin${base}/limits`);
  return (
    <>
      <Link prefetch={false} className="breadcrumb" href={orgBase}>
        {org} / Teams /
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">TEAM</p>
          <h1>{team}</h1>
          <p className="muted">Control application access, rate limits and spend.</p>
        </div>
      </div>
      <DataState {...exists} />
      {exists.data && (
        <>
          <nav className="tabs" aria-label="Team sections">
            {[
              ["keys", "API keys"],
              ["limits", "Limits"],
              ["budget", "Budget"],
            ].map(([value, label]) => (
              <button
                key={value}
                aria-current={tab === value ? "page" : undefined}
                onClick={() => setTab(value)}
              >
                {label}
              </button>
            ))}
          </nav>
          {tab === "keys" && <TeamKeys base={base} orgBase={orgBase} team={team} />}
          {tab === "limits" && <TeamLimits base={base} />}
          {tab === "budget" && <TeamBudget base={base} orgBase={orgBase} team={team} />}
        </>
      )}
    </>
  );
}
