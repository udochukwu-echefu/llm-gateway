"use client";
import { useRef, useState } from "react";
import { BrowserApiError, browserApi } from "@/lib/browser-api";
import { Dialog } from "./dialog";
export function CachePurge({ org, team }: { org: string; team?: string }) {
  const name = team ?? org;
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const lock = useRef(false);
  function close() {
    if (lock.current) return;
    setOpen(false);
    setTyped("");
  }
  async function purge() {
    if (typed !== name || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await browserApi<{ purged: number }>(
        `/api/admin/orgs/${encodeURIComponent(org)}/cache/purge${team ? `?team=${encodeURIComponent(team)}` : ""}`,
        { method: "POST" },
      );
      setMessage(`Purged ${result.purged} cached responses.`);
      setOpen(false);
      setTyped("");
    } catch (e) {
      setError(
        e instanceof BrowserApiError && e.status === 503
          ? "Redis is unavailable. Cache purge could not be completed. Try again when Redis recovers."
          : (e as Error).message,
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <section className="panel danger-zone" aria-label="Cache purge">
      <h2>Cache purge</h2>
      <p>
        Remove cached responses for {team ? `team ${team}` : `all teams in organisation ${org}`}.
        This does not delete usage records or change policies.
      </p>
      <p className="muted">
        Purge is best effort: new requests can refill the cache while it runs. Stop writers first if
        you need strict invalidation. Every successful purge is audited.
      </p>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
      <button
        className="danger"
        onClick={() => {
          setTyped("");
          setError("");
          setOpen(true);
        }}
      >
        Purge cache
      </button>
      {open && (
        <Dialog title={`Purge cache · ${name}`} onClose={close}>
          <p>Cached responses will be removed. New requests can refill them immediately.</p>
          <label>
            Type {name} to confirm
            <input
              autoComplete="off"
              value={typed}
              disabled={busy}
              onChange={(e) => setTyped(e.target.value)}
            />
          </label>
          <div className="actions">
            <button className="secondary" disabled={busy} onClick={close}>
              Cancel
            </button>
            <button
              className="danger"
              disabled={busy || typed !== name}
              onClick={() => void purge()}
            >
              Confirm purge
            </button>
          </div>
          {error && <p role="alert">{error}</p>}
        </Dialog>
      )}
    </section>
  );
}
