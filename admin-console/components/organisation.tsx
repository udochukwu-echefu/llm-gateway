"use client";
import Link from "next/link";
import { useState } from "react";
import type { NamedResource, Page } from "@/lib/contracts";
import { useResource } from "./use-resource";
import { DataState } from "./data-state";
import { MutationForm } from "./mutation-form";
import { UsageOverview } from "./usage-overview";
import { Policies } from "./policies";
import { CachePurge } from "./cache-purge";
import { usePolicyNavigation } from "./unsaved-policy";
export function Organisation({ org }: { org: string }) {
  const [cursor, setCursor] = useState("");
  const [tab, setTab] = useState("overview");
  const leave = usePolicyNavigation();
  const [version, setVersion] = useState(0);
  const base = `/orgs/${encodeURIComponent(org)}`;
  const teams = useResource<Page<NamedResource>>(
    `/api/admin${base}/teams?page_size=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
  );
  return (
    <>
      <Link prefetch={false} className="breadcrumb" href="/orgs">
        Organisations /
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ORGANISATION</p>
          <h1>{org}</h1>
          <p className="muted">Your teams, usage and monthly spending.</p>
        </div>
      </div>
      <DataState {...teams} />
      {teams.data && (
        <>
          <nav className="tabs" aria-label="Organisation sections">
            {[
              ["overview", "Overview"],
              ["policies", "Policies"],
              ["cache", "Cache"],
            ].map(([value, label]) => (
              <button
                key={value}
                aria-current={tab === value ? "page" : undefined}
                onClick={() => {
                  if (tab !== value && leave()) setTab(value);
                }}
              >
                {label}
              </button>
            ))}
          </nav>
          {tab === "policies" && <Policies org={org} />}
          {tab === "cache" && <CachePurge org={org} />}
          {tab === "overview" && (
            <>
              <section className="panel">
                <h2>Teams</h2>
                <MutationForm
                  path={`${base}/teams`}
                  label="Create team"
                  fields={[{ name: "name", label: "Team name" }]}
                  onSuccess={() => {
                    teams.refresh();
                    setVersion((v) => v + 1);
                  }}
                />
                {teams.data.data.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Team</th>
                        <th>Created</th>
                        <th>Team ID</th>
                      </tr>
                    </thead>
                    <tbody>
                      {teams.data.data.map((team) => (
                        <tr key={team.id}>
                          <td>
                            <Link
                              prefetch={false}
                              href={`${base}/teams/${encodeURIComponent(team.name)}`}
                            >
                              {team.name}
                            </Link>
                          </td>
                          <td>{team.created_at?.slice(0, 10)}</td>
                          <td>
                            <code>{team.id}</code>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="empty">
                    Create your first team using the form above. A team groups application keys,
                    policies and budgets.
                  </p>
                )}
                <div className="actions">
                  {cursor && (
                    <button className="secondary" onClick={() => setCursor("")}>
                      First page
                    </button>
                  )}
                  {teams.data.next_cursor && (
                    <button
                      className="secondary"
                      onClick={() => setCursor(String(teams.data!.next_cursor))}
                    >
                      Next teams
                    </button>
                  )}
                </div>
              </section>
              <UsageOverview key={version} org={org} />
            </>
          )}
        </>
      )}
    </>
  );
}
