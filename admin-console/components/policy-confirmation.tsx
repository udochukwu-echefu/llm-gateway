"use client";
import { Dialog } from "./dialog";
export function PolicyConfirmation({
  consequence,
  level,
  onClose,
  onConfirm,
  busy,
}: {
  consequence: string;
  level: string;
  onClose: () => void;
  onConfirm: () => void;
  busy: boolean;
}) {
  return (
    <Dialog title={`Confirm policy change · ${level}`} onClose={onClose}>
      <p>{consequence}</p>
      <div className="actions">
        <button className="secondary" onClick={onClose}>
          Cancel
        </button>
        <button className="danger" disabled={busy} onClick={onConfirm}>
          Confirm change
        </button>
      </div>
    </Dialog>
  );
}
