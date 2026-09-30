"use client";
import { useState } from "react";
export const firstRequest = `curl http://localhost:8000/v1/chat/completions \\
  -H 'Authorization: Bearer YOUR_TEAM_API_KEY' \\
  -H 'Content-Type: application/json' \\
  -d '{"model":"groq/openai/gpt-oss-20b","messages":[{"role":"user","content":"Hello from my first request"}]}'`;
export function UsageEmpty() {
  const [message, setMessage] = useState("");
  return (
    <div className="empty-state">
      <h3>No usage yet</h3>
      <p>
        Create a team and an API key, then send your first request to the public gateway. Replace
        YOUR_TEAM_API_KEY privately and use a model your policies allow. Your provider must be
        configured.
      </p>
      <pre className="request-example">
        <code>{firstRequest}</code>
      </pre>
      <button
        className="secondary"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(firstRequest);
            setMessage("Example copied. Replace the placeholder key privately.");
          } catch {
            setMessage("Copy is unavailable. Select and copy the example above.");
          }
        }}
      >
        Copy example request
      </button>
      {message && <p role="status">{message}</p>}
      <p className="muted">
        Usage appears after receipts are written. Examples contain a placeholder, never a real key.
      </p>
    </div>
  );
}
