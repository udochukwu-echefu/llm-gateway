/* Full navigation after auth changes discards the old page and any one-time key in memory. */
/* eslint-disable @next/next/no-location-assign-relative-destination */
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import type { Identity } from "@/lib/contracts";
import { UnsavedPolicies, usePolicyNavigation } from "./unsaved-policy";
import { browserApi } from "@/lib/browser-api";
export function Shell(props: { identity: Identity; children: ReactNode }) {
  return (
    <UnsavedPolicies>
      <ShellContent {...props} />
    </UnsavedPolicies>
  );
}
function ShellContent({ identity, children }: { identity: Identity; children: ReactNode }) {
  const leave = usePolicyNavigation();
  const path = usePathname();
  const [error, setError] = useState("");
  return (
    <div className="console">
      <a href="#main" className="skip">
        Skip to content
      </a>
      <aside>
        <div className="sidebar-content">
          <Link prefetch={false} className="brand" href="/orgs">
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
                identity.role === "org" && identity.organization
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
          </nav>
          <div className="sidebar-footer">
            <span className="badge">
              {identity.role === "platform" ? "Platform admin" : "Organisation admin"}
            </span>
            <p>{identity.name}</p>
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
                defaultValue="system"
                onChange={(e) =>
                  document.documentElement.setAttribute("data-theme", e.target.value)
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
          {error && <p role="alert">{error}</p>}
          {children}
        </main>
        <footer>Private administration · All changes are audited</footer>
      </div>
    </div>
  );
}
