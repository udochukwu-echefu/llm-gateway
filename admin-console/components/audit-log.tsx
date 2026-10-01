"use client";
import { useState } from "react";
import type { AuditEvent } from "@/lib/contracts";
import { browserApi } from "@/lib/browser-api";
import { usePagedResource } from "./use-paged-resource";
import { useListQuery } from "./use-list-query";
import { listSort } from "@/lib/list-query";
import { FilterBar, SortHeading, PageCount } from "./list-controls";
import { RecordTime } from "./record-time";
import { CopyId } from "./copy-id";
import { Dialog, SheetCloseButton } from "./dialog";
import { auditActions } from "@/lib/audit-actions";
import { DataState } from "./data-state";
import { SparkleButton } from "./sparkle-button";
export function AuditLog({ platform }: { platform: boolean }) {
  const { params } = useListQuery();
  const [detail, setDetail] = useState<AuditEvent>();
  const [verification, setVerification] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const query = new URLSearchParams(
    Array.from(params).filter(([key]) =>
      ["action", "actor", "target_type", "since", "until"].includes(key),
    ),
  );
  query.set("page_size", "25");
  const events = usePagedResource<AuditEvent>(`/api/admin/audit?${query}`);
  const rows = listSort(
    events.data,
    (params.get("sort") ?? "occurred_at") as keyof AuditEvent,
    params.get("direction") ?? "desc",
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ACCOUNTABILITY</p>
          <h1>Audit log</h1>
          <p className="muted">A durable record of changes and the administrators who made them.</p>
        </div>
        {platform && (
          <button
            className="secondary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                const result = await browserApi<{
                  valid: boolean;
                  events: number;
                  first_broken_id: number | null;
                }>("/api/admin/audit/verify");
                setVerification(
                  result.valid
                    ? `Chain verified: ${result.events} events are valid.`
                    : `Chain broken at event ${result.first_broken_id}.`,
                );
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Verify chain
          </button>
        )}
      </div>
      <section className="panel">
        <h2>Events</h2>
        <FilterBar
          submitButton={<SparkleButton text="Apply filters" />}
          fields={[
            { name: "action", label: "Action", options: auditActions },
            { name: "actor", label: "Actor" },
            {
              name: "target_type",
              label: "Target type",
              options: ["organization", "team", "key", "admin-key"],
            },
            { name: "since", label: "From date (UTC)", type: "date" },
            { name: "until", label: "To date (UTC)", type: "date" },
          ]}
        />
        <a className="button secondary" href={`/api/export/audit?${query}`}>
          Export CSV (up to 10,000 events)
        </a>
        <p role="status">{verification}</p>
        {error && <p role="alert">{error}</p>}
        <DataState {...events} />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <SortHeading field="occurred_at">Time</SortHeading>
                <SortHeading field="actor">Actor</SortHeading>
                <SortHeading field="action">Action</SortHeading>
                <SortHeading field="target_id">Target</SortHeading>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((event) => (
                <tr
                  key={event.id}
                  className="detail-row"
                  onClick={(click) => {
                    if (!(click.target as Element).closest("button, a, input")) setDetail(event);
                  }}
                >
                  <td>
                    <RecordTime value={event.occurred_at} />
                  </td>
                  <td>{event.actor}</td>
                  <td>{event.action}</td>
                  <td>
                    {event.target_type}
                    <br />
                    <CopyId value={event.target_id} />
                  </td>
                  <td>
                    <button className="secondary row-detail" onClick={() => setDetail(event)}>
                      Event {event.id}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!events.loading && !rows.length && (
          <p className="empty">
            No audit results match this filter. Try another action or date, or clear the fields and
            filter again.
          </p>
        )}
        <PageCount
          shown={rows.length}
          total={events.total}
          more={!!events.cursor}
          onMore={events.more}
        />
        {detail && (
          <Dialog
            drawer
            dismissOnBackdrop
            title={`Audit event ${detail.id}`}
            onClose={() => setDetail(undefined)}
          >
            <div className="sheet-summary">
              <span className="eyebrow">AUDIT RECORD</span>
              <h3>{detail.action}</h3>
              <p>by {detail.actor}</p>
              <RecordTime value={detail.occurred_at} />
            </div>
            <section className="sheet-section">
              <h3>Target</h3>
              <p className="muted">{detail.target_type}</p>
              <CopyId value={detail.target_id} />
            </section>
            <section className="sheet-section">
              <h3>Event metadata</h3>
              <pre className="sheet-code">{JSON.stringify(detail.details ?? {}, null, 2)}</pre>
            </section>
            <div className="sheet-footer">
              <SheetCloseButton />
            </div>
          </Dialog>
        )}
      </section>
    </>
  );
}
