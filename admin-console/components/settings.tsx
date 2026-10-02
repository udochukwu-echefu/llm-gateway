"use client";
import { Select } from "./select";
/* eslint-disable @next/next/no-location-assign-relative-destination */
import type { Identity } from "@/lib/contracts";
import { ABSOLUTE_MS, DEMO_ABSOLUTE_MS, IDLE_MS } from "@/lib/session-policy";
import { usePreferences } from "./preferences";
import { RecordTime } from "./record-time";
import { CopyId } from "./copy-id";
import { useResource } from "./use-resource";
import { DataState } from "./data-state";
import { browserApi } from "@/lib/browser-api";
import { useState } from "react";
export function Settings({
  identity,
  issuedAt,
  lastSeen,
  demo = false,
}: {
  identity: Identity;
  issuedAt: number;
  lastSeen: number;
  demo?: boolean;
}) {
  const { value, update } = usePreferences();
  const [error, setError] = useState("");
  return (
    <>
      <div className="screen-heading">
        <h1>Settings</h1>
      </div>
      <section className="panel settings-panel">
        <h2>Account</h2>
        <dl>
          <dt>Name</dt>
          <dd className="identity-name" title={identity.name}>
            {identity.name}
          </dd>
          <dt>Role</dt>
          <dd>{identity.role}</dd>
          <dt>Key ID</dt>
          <dd>
            <CopyId value={identity.key_id} />
          </dd>
          <dt>Organisation</dt>
          <dd>{identity.organization?.name ?? "All organisations"}</dd>
          <dt>Session started</dt>
          <dd>
            <RecordTime value={new Date(issuedAt).toISOString()} />
          </dd>
          <dt>Absolute expiry</dt>
          <dd>
            <RecordTime
              value={new Date(issuedAt + (demo ? DEMO_ABSOLUTE_MS : ABSOLUTE_MS)).toISOString()}
            />
          </dd>
          <dt>Idle expiry</dt>
          <dd>
            <RecordTime value={new Date(lastSeen + IDLE_MS).toISOString()} /> (refreshed by
            authenticated activity)
          </dd>
        </dl>
        <button
          onClick={async () => {
            try {
              await browserApi("/api/auth/logout", { method: "POST" });
              window.location.assign("/login");
            } catch (error) {
              setError((error as Error).message);
            }
          }}
        >
          Sign out of this session
        </button>
        {error && <p role="alert">{error}</p>}
      </section>
      <section className="panel settings-panel">
        <h2>Preferences</h2>
        <p>Saved only in this browser.</p>
        <div className="filter-bar">
          <label>
            Theme
            <Select
              aria-label="Theme"
              value={value.theme}
              onValueChange={(next) => update({ theme: next as typeof value.theme })}
            >
              {["system", "light", "dark"].map((item) => (
                <option key={item}>{item}</option>
              ))}
            </Select>
          </label>
          <label>
            Time display
            <Select
              aria-label="Time display"
              value={value.time}
              onValueChange={(next) => update({ time: next as typeof value.time })}
            >
              <option value="utc">UTC</option>
              <option value="local">
                Local ({Intl.DateTimeFormat().resolvedOptions().timeZone})
              </option>
            </Select>
          </label>
          <label>
            Table density
            <Select
              aria-label="Table density"
              value={value.density}
              onValueChange={(next) => update({ density: next as typeof value.density })}
            >
              {["comfortable", "compact"].map((item) => (
                <option key={item}>{item}</option>
              ))}
            </Select>
          </label>
          <label>
            Default landing page
            <Select
              aria-label="Default landing page"
              value={value.landing}
              onValueChange={(next) => update({ landing: next as typeof value.landing })}
            >
              {["/overview", "/requests", "/analytics", "/keys", "/models", "/settings"].map(
                (item) => (
                  <option key={item}>{item}</option>
                ),
              )}
            </Select>
          </label>
        </div>
      </section>
      {!identity.organization && <PlatformSettings />}
    </>
  );
}
function PlatformSettings() {
  const resource = useResource<Record<string, unknown>>("/api/admin/settings");
  return (
    <section className="panel settings-panel">
      <h2>Platform</h2>
      <p>
        Read-only effective configuration. Settings come from environment variables and change
        through a deploy, not through the console.
      </p>
      <DataState {...resource} />
      {resource.data && (
        <dl>
          {Object.entries(resource.data).map(([name, value]) => (
            <div key={name}>
              <dt>{name.replaceAll("_", " ")}</dt>
              <dd>
                <pre>
                  {typeof value === "object" ? JSON.stringify(value, null, 2) : String(value)}
                </pre>
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
