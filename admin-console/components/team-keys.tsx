"use client";
import { useState } from "react";
import type { KeyRecord, Page } from "@/lib/contracts";
import { browserApi } from "@/lib/browser-api";
import { useResource } from "./use-resource";
import { KeyInventory } from "./key-inventory";
import { MutationForm } from "./mutation-form";
import { KeyCreatedDialog } from "./key-created-dialog";
import { RevokeDialog } from "./revoke-dialog";
export function TeamKeys({ base, orgBase, team }: { base: string; orgBase: string; team: string }) {
  const [version, setVersion] = useState(0);
  const cursor = "";
  const cursorQuery = cursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
  const keyQuery = `team=${encodeURIComponent(team)}&page_size=25${cursorQuery}`;
  const keys = useResource<Page<KeyRecord>>(`/api/admin${orgBase}/keys?${keyQuery}`);
  const [secret, setSecret] = useState<string>();
  const [revoke, setRevoke] = useState<string>();
  const [notice, setNotice] = useState("");
  return (
    <section className="panel">
      <h2>API keys</h2>
      <p className="muted">
        Issue a separate key for each application. Full keys are displayed once.
      </p>
      <MutationForm
        path={`${base}/keys`}
        label="Create API key"
        fields={[
          { name: "name", label: "Key name" },
          {
            name: "expires_in_days",
            label: "Expires in days",
            type: "integer",
            optional: true,
            hint: "Leave blank for no expiry.",
          },
        ]}
        onSuccess={(body) => {
          keys.refresh();
          setVersion((value) => value + 1);
          if (typeof body.key === "string") setSecret(body.key);
          else
            setNotice(
              "This submission already created a key. Its secret cannot be recovered. Revoke it and create a new key.",
            );
        }}
      />
      {notice && <p role="status">{notice}</p>}
      <KeyInventory key={version} orgBase={orgBase} team={team} onRevoke={setRevoke} />
      {secret && <KeyCreatedDialog secret={secret} onClose={() => setSecret(undefined)} />}
      {revoke && (
        <RevokeDialog
          keyId={revoke}
          onClose={() => setRevoke(undefined)}
          onConfirm={async () => {
            await browserApi(`/api/admin/keys/${revoke}/revoke`, { method: "POST" });
            keys.refresh();
            setVersion((value) => value + 1);
          }}
        />
      )}
    </section>
  );
}
