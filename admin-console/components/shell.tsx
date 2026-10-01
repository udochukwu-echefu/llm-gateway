/* Full navigation after auth changes discards the old page and any one-time key in memory. */
/* eslint-disable @next/next/no-location-assign-relative-destination */
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import type { Identity } from "@/lib/contracts";
import { UnsavedPolicies, usePolicyNavigation } from "./unsaved-policy";
import { browserApi } from "@/lib/browser-api";
import { PreferencesProvider } from "./preferences";
import { GlobalCommands } from "./global-commands";
import { Toasts } from "./toasts";
import { Suspense } from "react";
import { Breadcrumbs } from "./breadcrumbs";
import { ReadOnlyProvider } from "./read-only";
import { ThemeToggle } from "./theme-toggle";
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
  const path = usePathname();
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  return (
    <div className={`console${collapsed ? " console-collapsed" : ""}`}>
      <a href="#main" className="skip">
        Skip to content
      </a>
      <aside id="gateway-sidebar" aria-label="Gateway sidebar">
        <div className="sidebar-panel">
          <div className="sidebar-content">
            <div className="sidebar-menu-header">
              <Link
                prefetch={false}
                className="sidebar-brand"
                href="/overview"
                aria-label="Runna Gateway Admin console"
                title={collapsed ? "Runna Gateway" : undefined}
              >
                <span className="sidebar-mark" aria-hidden="true" />
                <span className="sidebar-link-text">Runna Gateway</span>
              </Link>
              <button
                type="button"
                className="sidebar-toggle"
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                aria-expanded={!collapsed}
                aria-controls="gateway-sidebar"
                onClick={() => setCollapsed((value) => !value)}
              >
                <span className="sidebar-toggle-icon" aria-hidden="true" />
              </button>
            </div>
            <div className="scope-label">
              <small>Workspace scope</small>
              {identity.organization?.name ?? "All organisations"}
            </div>
            <p className="nav-label">WORKSPACE</p>
            <nav className="main-nav" aria-label="Main navigation">
              <Link
                prefetch={false}
                aria-current={path === "/overview" ? "page" : undefined}
                href="/overview"
                title={collapsed ? "Overview" : undefined}
              >
                <span className="nav-icon nav-icon-overview" aria-hidden="true" />
                <span className="sidebar-link-text">Overview</span>
              </Link>
              <Link
                prefetch={false}
                aria-current={path.startsWith("/orgs") ? "page" : undefined}
                title={collapsed ? "Organisations" : undefined}
                href={
                  identity.organization
                    ? `/orgs/${encodeURIComponent(identity.organization.name)}`
                    : "/orgs"
                }
              >
                <span className="nav-icon nav-icon-organisations" aria-hidden="true" />
                <span className="sidebar-link-text">Organisations</span>
              </Link>
              <Link
                prefetch={false}
                aria-current={path === "/audit" ? "page" : undefined}
                href="/audit"
                title={collapsed ? "Audit log" : undefined}
              >
                <span className="nav-icon nav-icon-audit" aria-hidden="true" />
                <span className="sidebar-link-text">Audit log</span>
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
                  title={collapsed ? label : undefined}
                  prefetch={false}
                  href={`/${label.toLowerCase()}`}
                  aria-current={path === `/${label.toLowerCase()}` ? "page" : undefined}
                >
                  <span className={`nav-icon nav-icon-${label.toLowerCase()}`} aria-hidden="true" />
                  <span className="sidebar-link-text">{label}</span>
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
              <small>Key ID · {identity.key_id}</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header>
          <span className="header-context">Gateway operations</span>
          <GlobalCommands identity={identity} />
          <div className="actions">
            <ThemeToggle />
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
