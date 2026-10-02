"use client";
import { OrgScope, useOrgScope } from "./org-scope";
import { KeyInventory } from "./key-inventory";
export function Keys() {
  const scope = useOrgScope();
  return (
    <>
      <div className="screen-heading">
        <h1>Keys</h1>
        <p>Organisation-wide key activity and expiry. Full key secrets are never shown here.</p>
      </div>
      <OrgScope {...scope} />
      {scope.org && (
        <section className="panel">
          <KeyInventory orgBase={`/orgs/${encodeURIComponent(scope.org)}`} />
        </section>
      )}
    </>
  );
}
