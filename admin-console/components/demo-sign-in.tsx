"use client";
/* eslint-disable @next/next/no-location-assign-relative-destination */
import { useState } from "react";
import { browserApi } from "@/lib/browser-api";

export function DemoSignIn({ org }: { org: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function explore(scope: "platform" | "org") {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await browserApi("/api/auth/demo", { method: "POST", body: JSON.stringify({ as: scope }) });
      window.location.assign("/overview");
    } catch (error) {
      setError((error as Error).message);
      setBusy(false);
    }
  }
  return (
    <div className="demo-sign-in">
      <button disabled={busy} onClick={() => void explore("platform")}>
        Explore as platform operator (read-only)
      </button>
      {org && (
        <button className="secondary" disabled={busy} onClick={() => void explore("org")}>
          Explore as Northwind Health org admin (read-only)
        </button>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
