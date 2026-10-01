/* Full navigation after auth changes discards the old page and any one-time key in memory. */
/* eslint-disable @next/next/no-location-assign-relative-destination */
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import type { Identity } from "@/lib/contracts";
import { UnsavedPolicies, usePolicyNavigation } from "./unsaved-policy";
import { browserApi } from "@/lib/browser-api";
import { PreferencesProvider, usePreferences } from "./preferences";
import { GlobalCommands } from "./global-commands";
import { Toasts } from "./toasts";
import { Suspense } from "react";
import { Breadcrumbs } from "./breadcrumbs";
import { ReadOnlyProvider } from "./read-only";
export function Shell(props: { identity: Identity; children: ReactNode }) {
  return (
    <ReadOnlyProvider viewer={props.identity.role === "viewer"}>
      <PreferencesProvider>
        <UnsavedPolicies>
          <ShellContent {...props} />
        </UnsavedPolicies>
      </PreferencesProvider>
    </ReadOnlyProvider>
  );
}
function ShellContent({ identity, children }: { identity: Identity; children: ReactNode }) {
  const leave = usePolicyNavigation();
  const preferences = usePreferences();
  const path = usePathname();
  const [error, setError] = useState("");
  return (
    <div className="console">
      <a href="#main" className="skip">
        Skip to content
      </a>
      <aside>
        <div className="sidebar-content">
          <Link prefetch={false} className="brand" href="/overview">
            <span className="brand-mark">g</span>gateway
            <span className="brand-sub">ADMIN CONSOLE</span>
          </Link>
          <p className="nav-label">WORKSPACE</p>
          <nav aria-label="Main navigation">
            <Link
              prefetch={false}
              aria-current={path === "/overview" ? "page" : undefined}
              href="/overview"
            >
              Overview
            </Link>
            <Link
              prefetch={false}
              aria-current={path.startsWith("/orgs") ? "page" : undefined}
              href={
                identity.organization
                  ? `/orgs/${encodeURIComponent(identity.organization.name)}`
                  : "/orgs"
              }
            >
              Organisations
            </Link>
            <Link
              prefetch={false}
              aria-current={path === "/audit" ? "page" : undefined}
              href="/audit"
            >
              Audit log
            </Link>
            {[
              "Requests",
              "Analytics",
              "Keys",
              "Models",
              ...(!identity.organization ? ["Providers"] : []),
              "Settings",
            ].map((label) => (
              <Link
                key={label}
                prefetch={false}
                href={`/${label.toLowerCase()}`}
                aria-current={path === `/${label.toLowerCase()}` ? "page" : undefined}
              >
                {label}
              </Link>
            ))}
          </nav>
          <div className="sidebar-footer">
            <span className="badge">
              {identity.role === "viewer"
                ? identity.organization
                  ? "Organisation viewer"
                  : "Platform viewer"
                : identity.role === "platform"
                  ? "Platform admin"
                  : "Organisation admin"}
            </span>
            <p className="identity-name" title={identity.name}>
              {identity.name}
            </p>
            <small>Key ID · {identity.key_id}</small>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header>
          <span className="muted">Gateway operations</span>
          <div className="actions">
            <label className="theme-label">
              Theme
              <select
                aria-label="Theme"
                value={preferences.value.theme}
                onChange={(e) =>
                  preferences.update({ theme: e.target.value as "system" | "light" | "dark" })
                }
              >
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
            <button
              className="secondary"
              onClick={async () => {
                if (!leave()) return;
                try {
                  await browserApi("/api/auth/logout", { method: "POST" });
                  window.location.assign("/login");
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Sign out
            </button>
          </div>
        </header>
        <main id="main">
          {identity.role === "viewer" && (
            <p className="demo-banner" role="status">
              Read-only demo. Changes are disabled; this is a live gateway with synthetic data.
            </p>
          )}
          {error && <p role="alert">{error}</p>}
          <Breadcrumbs />
          <GlobalCommands identity={identity} />
          <Suspense
            fallback={
              <div className="skeleton" role="status">
                Loading…
              </div>
            }
          >
            {children}
          </Suspense>
          <Toasts />
        </main>
        <footer>Private administration · All changes are audited</footer>
      </div>
    </div>
  );
}
