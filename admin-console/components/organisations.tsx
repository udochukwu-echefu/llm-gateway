"use client";
import Link from "next/link";
import { useState } from "react";
import type { NamedResource, Page } from "@/lib/contracts";
import { useResource } from "./use-resource";
import { DataState } from "./data-state";
import { MutationForm } from "./mutation-form";
export function Organisations() {
  const [cursor, setCursor] = useState("");
  const resource = useResource<Page<NamedResource>>(
    `/api/admin/orgs?page_size=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
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
            setCursor("");
            resource.refresh();
          }}
        />
      </section>
      <section className="panel">
        <h2>Organisations</h2>
        <DataState {...resource} />
        {resource.data &&
          (resource.data.data.length ? (
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Created</th>
                  <th>Organisation ID</th>
                </tr>
              </thead>
              <tbody>
                {resource.data.data.map((org) => (
                  <tr key={org.id}>
                    <td>
                      <Link prefetch={false} href={`/orgs/${encodeURIComponent(org.name)}`}>
                        {org.name}
                      </Link>
                    </td>
                    <td>{org.created_at?.slice(0, 10)}</td>
                    <td>
                      <code>{org.id}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="empty">
              No organisations yet. Create your first organisation using the form above. Create one
              to get started.
            </p>
          ))}
        <div className="actions">
          {cursor && (
            <button className="secondary" onClick={() => setCursor("")}>
              First page
            </button>
          )}
          {resource.data?.next_cursor && (
            <button
              className="secondary"
              onClick={() => setCursor(String(resource.data!.next_cursor))}
            >
              Next organisations
            </button>
          )}
        </div>
      </section>
    </>
  );
}
