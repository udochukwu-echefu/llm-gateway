"use client";
import { useState } from "react";
import type { AuditEvent, Page } from "@/lib/contracts";
import { browserApi } from "@/lib/browser-api";
import { useResource } from "./use-resource";
import { DataState } from "./data-state";
export function AuditLog({ platform }: {
  platform: boolean;
}) {
  const [filters, setFilters] = useState({ action: "", since: "" });
  const [cursor, setCursor] = useState("");
  const [verification, setVerification] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const query = new URLSearchParams({ page_size: "25", ...(filters.action && { action: filters.action }), ...(filters.since && { since: filters.since }), ...(cursor && { cursor }) });
  const events = useResource<Page<AuditEvent>>(`/api/admin/audit?${query}`);
  return <>
    <div className="page-heading">
      <div>
        <p className="eyebrow">ACCOUNTABILITY</p>
        <h1>Audit log</h1>
        <p className="muted">A durable record of changes and the administrators who made them.</p>
      </div>{platform && <button className="secondary" disabled={busy} onClick={async () => {
        setBusy(true); setError(""); try {
          const result = await browserApi<{
            valid: boolean;
            events: number;
            first_broken_id: number | null;
          }>("/api/admin/audit/verify");
          setVerification(result.valid ? `Chain verified: ${result.events} events are valid.` : `Chain broken at event ${result.first_broken_id}.`);
        }
          catch (e) {
            setError((e as Error).message);
          }
          finally {
          setBusy(false);
        }
      }}>Verify chain</button>}</div>
    <section className="panel">
      <h2>Events</h2>
      <form className="mutation-form" onSubmit={(e) => { e.preventDefault(); const form = new FormData(e.currentTarget); setFilters({ action: String(form.get("action") ?? ""), since: String(form.get("since") ?? "") }); setCursor(""); }}>
        <label>Action<input name="action" placeholder="e.g. create-team" />
        </label>
        <label>From date (UTC)<input name="since" type="date" />
        </label>
        <button>Filter events</button>
      </form>
      <p role="status">{verification}</p>{error && <p role="alert">{error}</p>}<DataState {...events} />{events.data && (events.data.data.length ? <table>
        <thead>
          <tr>
            <th>Time (UTC)</th>
            <th>Actor</th>
            <th>Action</th>
            <th>Target</th>
          </tr>
        </thead>
        <tbody>{events.data.data.map((event) => <tr key={event.id}>
          <td>
            <time dateTime={event.occurred_at}>{event.occurred_at.slice(0, 19).replace("T", " ")}</time>
          </td>
          <td>
            <code>{event.actor}</code>
          </td>
          <td>{event.action}</td>
          <td>{event.target_type}<br />
            <code>{event.target_id}</code>
          </td>
        </tr>)}</tbody>
      </table> : <p className="empty">No events match these filters.</p>)}
      <div className="actions">{cursor && <button className="secondary" onClick={() => setCursor("")}>First page</button>}{events.data?.next_cursor && <button className="secondary" onClick={() => setCursor(String(events.data!.next_cursor))}>Next events</button>}</div>
    </section>
  </>;
}
