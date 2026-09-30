"use client";
import { useRef, useState } from "react";
import { browserApi } from "@/lib/browser-api";
import { operationSchema, isCreation } from "@/lib/bff-policy";
import { submissionId } from "@/lib/submission";
export interface Field {
  name: string;
  label: string;
  value?: string;
  type?: "text" | "integer" | "decimal";
  optional?: boolean;
  hint?: string;
}
export function MutationForm({ path, method = "POST", fields, label, onSuccess }: {
  path: string;
  method?: string;
  fields: Field[];
  label: string;
  onSuccess: (body: Record<string, unknown>) => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const id = useRef(submissionId());
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lock.current)
      return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const body = Object.fromEntries(fields.map((f) => { const value = String(values.get(f.name) ?? "").trim(); return [f.name, f.type === "integer" ? (value ? Number(value) : null) : value]; }));
    const schema = operationSchema(method, path);
    if (!schema?.safeParse(body).success) {
      setError("Check the form values. Names are required; limits must be whole non-negative numbers, budgets decimal amounts, and thresholds greater than 0 and at most 1.");
      return;
    }
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await browserApi<Record<string, unknown>>(`/api/admin${path}`, { method, body: JSON.stringify(body), headers: isCreation(method, path) ? { "Idempotency-Key": id.current.begin() } : {} });
      id.current.finish();
      form.reset();
      onSuccess(result);
    }
    catch (e) {
      setError((e as Error).message);
    }
    finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return <form onSubmit={submit} onChange={() => id.current.finish()} className="mutation-form" noValidate>
    {fields.map((field) => <label key={field.name}>{field.label}<input name={field.name} defaultValue={field.value ?? ""} required={!field.optional} type="text" inputMode={field.type === "integer" ? "numeric" : field.type === "decimal" ? "decimal" : "text"} autoComplete="off" disabled={busy} aria-describedby={field.hint ? `${field.name}-hint` : undefined} />{field.hint && <small id={`${field.name}-hint`}>{field.hint}</small>}</label>)}
    <button disabled={busy} type="submit">{busy ? "Saving…" : label}</button>{error && <p role="alert" className="error">{error}</p>}
  </form>;
}
