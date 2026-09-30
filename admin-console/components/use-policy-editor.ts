"use client";
import { useRef, useState } from "react";
import { BrowserApiError, browserApi } from "@/lib/browser-api";
import { useUnsavedPolicy } from "./unsaved-policy";
export function usePolicyEditor<T extends { version: string }, D>(
  path: string,
  initial: T,
  draftOf: (view: T) => D,
  changesOf: (view: T, draft: D) => string[],
) {
  const [view, setView] = useState(initial);
  const [draft, setDraft] = useState(() => draftOf(initial));
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const lock = useRef(false);
  const changes = changesOf(view, draft);
  useUnsavedPolicy(path, changes.length > 0);
  async function reload() {
    if (lock.current) return;
    if (changes.length && !window.confirm("Reload and discard your unsaved edits?")) return;
    await execute(async () => {
      const next = await browserApi<T>(path);
      setView(next);
      setDraft(draftOf(next));
      setConflict(false);
    });
  }
  async function save(body: object | null) {
    if (lock.current || conflict) return;
    await execute(async () => {
      await browserApi(path, {
        method: body === null ? "DELETE" : "PUT",
        headers: { "If-Match": `"${view.version}"` },
        body: body === null ? undefined : JSON.stringify(body),
      });
      // Keep the old version until a fresh API view succeeds; a failed read requires reload.
      setConflict(true);
      const next = await browserApi<T>(path);
      setView(next);
      setDraft(draftOf(next));
      setConflict(false);
      setNotice(
        "Policy saved. Enforcement may take up to the configured key-cache TTL (normally 30 seconds).",
      );
    });
  }
  async function execute(work: () => Promise<void>) {
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
    } catch (e) {
      if (e instanceof BrowserApiError && e.status === 412) setConflict(true);
      else setError((e as Error).message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return { view, draft, setDraft, changes, error, conflict, busy, notice, reload, save };
}
