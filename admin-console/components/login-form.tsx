/* Full navigation after auth changes discards the old page and any one-time key in memory. */
/* eslint-disable @next/next/no-location-assign-relative-destination */
"use client";
import { useState } from "react";
export function LoginForm() {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="login-form"
      onSubmit={async (event) => {
        event.preventDefault();
        setError("");
        setBusy(true);
        const form = event.currentTarget;
        const input = form.elements.namedItem("key") as HTMLInputElement;
        const key = input.value.trim();
        input.value = "";
        try {
          const response = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ key }),
          });
          const body = await response.json();
          if (!response.ok) throw new Error(body.error);
          input.value = "";
          window.location.assign("/overview");
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <label>
        Admin API key
        <input
          name="key"
          type="password"
          autoComplete="off"
          spellCheck={false}
          required
          placeholder="lgwa_…"
        />
      </label>
      <p className="muted">
        Use a platform or organisation admin key issued by your gateway operator.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form>
  );
}
