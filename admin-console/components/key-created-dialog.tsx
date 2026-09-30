"use client";
import { useState } from "react";
import { Dialog } from "./dialog";
export function KeyCreatedDialog({ secret, onClose }: { secret: string; onClose: () => void }) {
  const [message, setMessage] = useState("");
  return (
    <Dialog title="Save your API key" onClose={onClose}>
      <p>You won’t see this again. Copy it to your secure secret store before closing.</p>
      <code className="secret" data-testid="created-key">
        {secret}
      </code>
      <div className="actions">
        <button
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(secret);
              setMessage("Copied.");
            } catch {
              setMessage("Copy unavailable. Select the key and copy it manually.");
            }
          }}
        >
          Copy key
        </button>
        <button className="secondary" onClick={onClose}>
          I saved the key
        </button>
      </div>
      <p role="status">{message}</p>
    </Dialog>
  );
}
