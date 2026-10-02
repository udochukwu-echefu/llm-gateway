"use client";
import { SortableTable } from "./sortable-table";
import Link from "next/link";
import { useEffect, useState } from "react";
import { loadOverview } from "@/lib/overview-data";
import { currentMonth } from "@/lib/usage-data";
import { MoneyValue } from "./money-value";
import { UsageEmpty } from "./usage-empty";
import { OverviewCards } from "./overview-cards";
import { OverviewBudgets } from "./overview-budgets";
import { UsageChart } from "./usage-chart";
import { DataState } from "./data-state";
export function Overview() {
  const [data, setData] = useState<Awaited<ReturnType<typeof loadOverview>>>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    let active = true;
    loadOverview()
      .then((result) => {
        if (active) setData(result);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">GATEWAY OPERATIONS · UTC</p>
          <h1>Overview</h1>
          <p className="muted">
            Your gateway at a glance · {currentMonth().since} — {currentMonth().until}
          </p>
        </div>
        <Link prefetch={false} href="/orgs">
          Manage organisations →
        </Link>
      </div>
      <DataState loading={!data && !error} error={error} />
      {data && (
        <>
          <OverviewCards summary={data.summary} />
          <section className="panel">
            <h2>Organisations</h2>
            {data.organizations.length ? (
              <div className="workspace-links">
                {data.organizations.map(({ org, budgets }) => (
                  <Link
                    prefetch={false}
                    key={org.id}
                    href={`/orgs/${encodeURIComponent(org.name)}`}
                  >
                    <strong>{org.name}</strong>
                    <small>{budgets.length} teams</small>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="empty">No organisations yet. Create one from Manage organisations.</p>
            )}
          </section>
          <div className="overview-grid">
            <section className="panel overview-chart-panel">
              <h2>Requests over time</h2>
              {data.byDay.length ? (
                <>
                  <UsageChart
                    title="Daily requests"
                    unit="Requests"
                    days={data.byDay.map((r) => r.group)}
                    values={data.byDay.map((r) => r.requests)}
                    marker="circle"
                  />
                  <details>
                    <summary>Daily request values</summary>
                    <SortableTable name="overview-1">
                      <thead>
                        <tr>
                          <th>Day (UTC)</th>
                          <th>Requests</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.byDay.map((row) => (
                          <tr key={row.group}>
                            <td>{row.group}</td>
                            <td>{row.requests}</td>
                          </tr>
                        ))}
                      </tbody>
                    </SortableTable>
                  </details>
                </>
              ) : (
                <UsageEmpty />
              )}
            </section>
            <section className="panel overview-model-panel">
              <h2>Top 5 models by priced spend</h2>
              {data.models.length ? (
                <SortableTable name="overview-2">
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Requests</th>
                      <th>Priced spend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.models.map((row) => (
                      <tr key={row.group}>
                        <td>
                          <code>{row.group}</code>
                        </td>
                        <td>{row.requests}</td>
                        <td>
                          <MoneyValue value={row.cost_usd} />
                          {row.usage_missing + row.stream_incomplete > 0 && (
                            <small className="warning">Plus unpriced usage</small>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </SortableTable>
              ) : (
                <p className="empty">No model usage this month.</p>
              )}
            </section>
          </div>
          <OverviewBudgets rows={data.closest} />
          <section className="panel">
            <div className="section-heading">
              <h2>Recent audit events</h2>
              <Link prefetch={false} href="/audit">
                View full audit log →
              </Link>
            </div>
            {data.recent.length ? (
              <SortableTable name="overview-3">
                <thead>
                  <tr>
                    <th>Time (UTC)</th>
                    <th>Action</th>
                    <th>Actor</th>
                    <th>Target</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent.map((event) => (
                    <tr key={event.id}>
                      <td>
                        <time dateTime={event.occurred_at}>
                          {event.occurred_at.slice(0, 19).replace("T", " ")}
                        </time>
                      </td>
                      <td>{event.action}</td>
                      <td>{event.actor}</td>
                      <td>
                        {event.target_type} · <code>{event.target_id}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </SortableTable>
            ) : (
              <p className="empty">No audit events yet. Administrative changes will appear here.</p>
            )}
          </section>
        </>
      )}
    </>
  );
}
