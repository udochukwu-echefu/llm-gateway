"use client";
import type { Catalog, ListPolicy, GuardrailView } from "@/lib/policy-contracts";
import { useResource } from "./use-resource";
import { DataState } from "./data-state";
import { ListPolicyEditor } from "./list-policy-editor";
import { GuardrailsEditor } from "./guardrails-editor";
export function Policies({ org, team }: { org: string; team?: string }) {
  const base = `/api/admin/orgs/${encodeURIComponent(org)}`;
  const query = team ? `?team=${encodeURIComponent(team)}` : "";
  const path = (kind: string) => `${base}/${kind}${query}`;
  const catalog = useResource<Catalog>("/api/admin/catalog");
  const models = useResource<ListPolicy>(path("model-policy"));
  const guardrails = useResource<GuardrailView>(path("guardrails"));
  const residency = useResource<ListPolicy>(path("residency"));
  return (
    <>
      <p className="muted">
        Each save replaces the whole override at this level. Effective results come from the
        gateway.
      </p>
      <DataState {...catalog} />
      <DataState {...models} />
      <DataState {...guardrails} />
      <DataState {...residency} />
      {catalog.data && models.data && (
        <ListPolicyEditor
          kind="model-policy"
          path={path("model-policy")}
          initial={models.data}
          org={org}
          team={team}
          catalog={catalog.data}
        />
      )}
      {guardrails.data && (
        <GuardrailsEditor
          path={path("guardrails")}
          initial={guardrails.data}
          org={org}
          team={team}
        />
      )}
      {catalog.data && residency.data && (
        <ListPolicyEditor
          kind="residency"
          path={path("residency")}
          initial={residency.data}
          org={org}
          team={team}
          catalog={catalog.data}
        />
      )}
    </>
  );
}
