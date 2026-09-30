"use client";
import { useState } from "react";
import type { Limits, LimitName } from "@/lib/contracts";
import { browserApi } from "@/lib/browser-api";
import { useResource } from "./use-resource";
import { DataState } from "./data-state";
import { MutationForm } from "./mutation-form";
const names: Record<LimitName, string> = { rpm: "Requests per minute", tpm: "Tokens per minute", max_concurrency: "Max concurrency" };
export function TeamLimits({ base }: {
  base: string;
}) {
  const limits = useResource<Limits>(`/api/admin${base}/limits`);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return <section className="panel">
    <h2>Limits</h2>
    <p className="muted">Blank fields inherit the gateway defaults. A value of 0 means unlimited.</p>
    <DataState {...limits} />
    {limits.data && <>
      <table>
        <thead>
          <tr>
            <th>Limit</th>
            <th>Override</th>
            <th>Effective</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>{(Object.keys(names) as LimitName[]).map((key) => <tr key={key}>
          <td>{names[key]}</td>
          <td>{limits.data!.overrides[key] ?? "—"}</td>
          <td>{limits.data!.effective[key] === 0 ? "Unlimited" : limits.data!.effective[key]}</td>
          <td>{limits.data!.overrides[key] !== null ? "Override" : limits.data!.effective[key] === 0 ? "Unlimited" : "Default"}</td>
        </tr>)}</tbody>
      </table>
      <MutationForm key={JSON.stringify(limits.data.overrides)} path={`${base}/limits`} method="PUT" label="Save limits" fields={(Object.keys(names) as LimitName[]).map((key) => ({ name: key, label: names[key], type: "integer", optional: true, value: limits.data!.overrides[key]?.toString() ?? "" }))} onSuccess={() => { limits.refresh(); setNotice("Limits saved."); }} />
      <button className="secondary" disabled={busy} onClick={async () => {
        setBusy(true); setError(""); try {
          await browserApi(`/api/admin${base}/limits`, { method: "DELETE" });
          limits.refresh();
          setNotice("Overrides cleared.");
        }
          catch (e) {
            setError((e as Error).message);
          }
          finally {
          setBusy(false);
        }
      }}>Clear overrides</button>
    </>}
    <p role="status">{notice}</p>{error && <p role="alert">{error}</p>}
  </section>;
}
