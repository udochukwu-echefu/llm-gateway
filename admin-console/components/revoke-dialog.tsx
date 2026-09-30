"use client";
import { useState } from "react";
import { Dialog } from "./dialog";
export function RevokeDialog({ keyId, onClose, onConfirm }: {
  keyId: string;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <Dialog title="Revoke API key" onClose={onClose}>
    <p>Revoke <strong>{keyId}</strong>? Applications using this key will lose access after the gateway key cache expires.</p>
    <label className="check">
      <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />I confirm revocation of {keyId}</label>
    {error && <p role="alert">{error}</p>}
    <div className="actions">
      <button className="danger" disabled={!confirmed || busy} onClick={async () => {
        setBusy(true); try {
          await onConfirm();
          onClose();
        }
          catch (e) {
            setError((e as Error).message);
          }
          finally {
          setBusy(false);
        }
      }}>Confirm revoke</button>
      <button className="secondary" disabled={busy} onClick={onClose}>Cancel</button>
    </div>
  </Dialog>;
}
