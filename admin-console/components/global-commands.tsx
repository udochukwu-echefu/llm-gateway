"use client";
import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { Dialog } from "./dialog";
import { SearchInput } from "./search-input";
import type { Identity } from "@/lib/contracts";
import type { SearchResult } from "@/lib/console-contracts";
import { commandPages, resultUrl, scopedResults } from "@/lib/command-search";
import { browserApi } from "@/lib/browser-api";
export function GlobalCommands({ identity }: { identity: Identity }) {
  const [open, setOpen] = useState(false),
    [help, setHelp] = useState(false),
    [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]),
    [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const resultNav = useRef<HTMLElement>(null);
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      } else if (
        event.key === "?" &&
        !(
          event.target instanceof HTMLElement &&
          event.target.closest('input,textarea,select,[role="combobox"],[contenteditable]')
        )
      ) {
        event.preventDefault();
        setHelp(true);
      }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(async () => {
      if (!query.trim()) {
        setResults([]);
        setBusy(false);
        return;
      }
      setBusy(true);
      try {
        const response = await browserApi<{ data: SearchResult[] }>(
          `/api/admin/search?q=${encodeURIComponent(query)}`,
        );
        if (active) {
          setResults(scopedResults(response.data, identity));
          setError("");
        }
      } catch (error) {
        if (active) setError((error as Error).message);
      } finally {
        if (active) setBusy(false);
      }
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query, identity]);
  return (
    <>
      <div className="global-tools">
        <button className="secondary search-trigger" onClick={() => setOpen(true)}>
          Search · ⌘/Ctrl K
        </button>
        <button className="secondary" aria-label="Keyboard shortcuts" onClick={() => setHelp(true)}>
          ?
        </button>
      </div>
      {open && (
        <Dialog dismissOnBackdrop title="Go to…" onClose={() => setOpen(false)}>
          <SearchInput
            value={query}
            onChange={setQuery}
            busy={busy}
            onSubmit={() => resultNav.current?.querySelector<HTMLAnchorElement>("a")?.focus()}
          />
          {error && <p role="alert">{error}</p>}
          <nav ref={resultNav} aria-label="Search results">
            {[...commandPages, ...(!identity.organization ? ["Providers"] : [])]
              .filter((page) => page.toLowerCase().includes(query.toLowerCase()))
              .map((page) => (
                <Link
                  key={page}
                  href={
                    page === "Organisations"
                      ? identity.organization
                        ? `/orgs/${encodeURIComponent(identity.organization.name)}`
                        : "/orgs"
                      : `/${page.toLowerCase()}`
                  }
                  onClick={() => setOpen(false)}
                >
                  {page}
                </Link>
              ))}
            {results.map((item) => (
              <Link key={item.kind + item.id} href={resultUrl(item)} onClick={() => setOpen(false)}>
                {item.name}{" "}
                <small>
                  {item.kind} · {item.org} · {item.id}
                </small>
              </Link>
            ))}
          </nav>
          <button className="secondary" onClick={() => setOpen(false)}>
            Close
          </button>
        </Dialog>
      )}
      {help && (
        <Dialog title="Keyboard shortcuts" onClose={() => setHelp(false)}>
          <dl>
            <dt>Cmd/Ctrl + K</dt>
            <dd>Open global search</dd>
            <dt>?</dt>
            <dd>Show this help</dd>
            <dt>Escape</dt>
            <dd>Close a drawer or dialog</dd>
            <dt>Tab / Shift + Tab</dt>
            <dd>Move between controls</dd>
          </dl>
          <button onClick={() => setHelp(false)}>Close</button>
        </Dialog>
      )}
    </>
  );
}
