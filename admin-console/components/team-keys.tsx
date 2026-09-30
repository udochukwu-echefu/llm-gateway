"use client";
import { useState } from "react";
import type { KeyRecord, Page } from "@/lib/contracts";
import { browserApi } from "@/lib/browser-api";
import { useResource } from "./use-resource";
import { DataState } from "./data-state";
import { MutationForm } from "./mutation-form";
import { KeyCreatedDialog } from "./key-created-dialog";
import { RevokeDialog } from "./revoke-dialog";
export function TeamKeys({ base, orgBase, team }: {
  base: string;
  orgBase: string;
  team: string;
}) {
  const [cursor, setCursor] = useState("");
  const keys = useResource<Page<KeyRecord>>(`/api/admin${orgBase}/keys?team=${encodeURIComponent(team)}&page_size=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
  const [secret, setSecret] = useState<string>();
  const [revoke, setRevoke] = useState<string>();
  const [notice, setNotice] = useState("");
  return <section className="panel">
    <h2>API keys</h2>
    <p className="muted">Issue a separate key for each application. Full keys are displayed once.</p>
    <MutationForm path={`${base}/keys`} label="Create API key" fields={[{ name: "name", label: "Key name" }, { name: "expires_in_days", label: "Expires in days", type: "integer", optional: true, hint: "Leave blank for no expiry." }]} onSuccess={(body) => {
      keys.refresh(); if (typeof body.key === "string")
        setSecret(body.key);
      else
        setNotice("This submission already created a key. Its secret cannot be recovered. Revoke it and create a new key.");
    }} />
    {notice && <p role="status">{notice}</p>}<DataState {...keys} />{keys.data && (keys.data.data.length ? <table>
      <thead>
        <tr>
          <th>Name / key ID</th>
          <th>Status</th>
          <th>Created</th>
          <th>Expiry</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>{keys.data.data.map((key) => <tr key={key.id}>
        <td>{key.name}<br />
          <code>{key.key_id}</code>
        </td>
        <td>
          <span className="badge">{key.revoked_at ? "Revoked" : key.expires_at && Date.parse(key.expires_at) <= (keys.loadedAt ?? 0) ? "Expired" : "Active"}</span>
        </td>
        <td>{key.created_at?.slice(0, 10)}</td>
        <td>{key.expires_at?.slice(0, 10) ?? "No expiry"}</td>
        <td>
          <button className="secondary" disabled={Boolean(key.revoked_at)} onClick={() => setRevoke(key.key_id)}>Revoke {key.key_id}</button>
        </td>
      </tr>)}</tbody>
    </table> : <p className="empty">No API keys for this team.</p>)}
    <div className="actions">{cursor && <button className="secondary" onClick={() => setCursor("")}>First page</button>}{keys.data?.next_cursor && <button className="secondary" onClick={() => setCursor(String(keys.data!.next_cursor))}>Next keys</button>}</div>
    {secret && <KeyCreatedDialog secret={secret} onClose={() => setSecret(undefined)} />}
    {revoke && <RevokeDialog keyId={revoke} onClose={() => setRevoke(undefined)} onConfirm={async () => { await browserApi(`/api/admin/keys/${revoke}/revoke`, { method: "POST" }); keys.refresh(); }} />}
  </section>;
}
