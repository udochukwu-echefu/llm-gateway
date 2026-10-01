"use client";
import Link from "next/link";

import type { NamedResource } from "@/lib/contracts";
import { usePagedResource } from "./use-paged-resource";
import { useListQuery } from "./use-list-query";
import { listSort } from "@/lib/list-query";
import { SortHeading, PageCount } from "./list-controls";
import { RecordTime } from "./record-time";
import { CopyId } from "./copy-id";
import { DataState } from "./data-state";
import { MutationForm } from "./mutation-form";
export function Organisations() {
  const resource = usePagedResource<NamedResource>("/api/admin/orgs?page_size=25");
  const { params } = useListQuery();
  const rows = listSort(
    resource.data,
    (params.get("sort") ?? "name") as keyof NamedResource,
    params.get("direction") ?? "asc",
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">WORKSPACE</p>
          <h1>Organisations</h1>
          <p className="muted">Manage access and spending across your gateway.</p>
        </div>
      </div>
      <section className="panel">
        <h2>Create an organisation</h2>
        <MutationForm
          path="/orgs"
          label="Create organisation"
          fields={[{ name: "name", label: "Organisation name" }]}
          onSuccess={() => {
            resource.refresh();
          }}
        />
      </section>
      <section className="panel">
        <h2>Organisations</h2>
        <DataState {...resource} />
        {rows.length ? (
          <table>
            <thead>
              <tr>
                <SortHeading field="name">Name</SortHeading>
                <SortHeading field="created_at">Created</SortHeading>
                <SortHeading field="id">Organisation ID</SortHeading>
              </tr>
            </thead>
            <tbody>
              {rows.map((org) => (
                <tr key={org.id}>
                  <td>
                    <Link prefetch={false} href={`/orgs/${encodeURIComponent(org.name)}`}>
                      {org.name}
                    </Link>
                  </td>
                  <td>
                    <RecordTime value={org.created_at} />
                  </td>
                  <td>
                    <CopyId value={org.id} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="empty">
            No organisations yet. Create your first organisation using the form above. Create one to
            get started.
          </p>
        )}
        <PageCount
          shown={rows.length}
          total={resource.total}
          more={!!resource.cursor}
          onMore={resource.more}
        />
      </section>
    </>
  );
}
