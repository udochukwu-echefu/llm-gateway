"use client";
import { Select } from "./select";
import { useEffect, useState } from "react";
import { allPages } from "@/lib/usage-data";
import { DataState } from "./data-state";
import { useListQuery } from "./use-list-query";
import type { NamedResource } from "@/lib/contracts";
export function useOrgScope() {
  const { params } = useListQuery();
  const [result, setResult] = useState<{ data?: { data: NamedResource[] }; error?: string }>();
  useEffect(() => {
    let active = true;
    allPages<NamedResource>("/api/admin/orgs")
      .then((data) => {
        if (active) setResult({ data: { data } });
      })
      .catch((error: Error) => {
        if (active) setResult({ error: error.message });
      });
    return () => {
      active = false;
    };
  }, []);
  const orgs = { ...result, loading: !result };
  return { org: params.get("org") ?? orgs.data?.data[0]?.name, orgs };
}
export function OrgScope({ org, orgs }: ReturnType<typeof useOrgScope>) {
  const { set } = useListQuery();
  return (
    <div className="scope-toolbar">
      <DataState {...orgs} />
      <label>
        Organisation
        <Select
          aria-label="Organisation"
          value={org ?? ""}
          onValueChange={(next) => set({ org: next })}
        >
          <option value="" disabled>
            Choose an organisation
          </option>
          {orgs.data?.data.map((item) => (
            <option key={item.id} value={item.name}>
              {item.name}
            </option>
          ))}
        </Select>
      </label>
    </div>
  );
}
