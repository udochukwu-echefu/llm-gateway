"use client";
import { useEffect, useId, useRef } from "react";
import { SearchVisuals } from "./search-visuals";

export function SearchInput({
  value,
  onChange,
  busy,
  onSubmit,
}: {
  value: string;
  onChange: (value: string) => void;
  busy: boolean;
  onSubmit: () => void;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const energy = useRef(0);
  useEffect(() => {
    function focus(event: KeyboardEvent) {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
      if (
        event.target instanceof HTMLElement &&
        event.target.closest('input, textarea, select, [role="combobox"], [contenteditable]')
      )
        return;
      event.preventDefault();
      input.current?.focus();
    }
    window.addEventListener("keydown", focus);
    return () => window.removeEventListener("keydown", focus);
  }, []);
  return (
    <SearchVisuals busy={busy} energy={energy}>
      <form
        className="search-input-frame"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <label className="sr-only" htmlFor={id}>
          Search pages, organisations, teams and keys
        </label>
        <input
          ref={input}
          id={id}
          className="command-search-input"
          placeholder="Find a page, organisation, team or key…"
          autoComplete="off"
          spellCheck={false}
          maxLength={128}
          autoFocus
          value={value}
          onChange={(event) => {
            energy.current = Math.min(1, energy.current + 0.5);
            onChange(event.target.value);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.nativeEvent.isComposing) {
              event.preventDefault();
              onSubmit();
            }
            if (event.key === "Escape") {
              onChange("");
              input.current?.blur();
            }
          }}
        />
        <button
          type="submit"
          className="search-orb-button"
          aria-label={busy ? "Searching" : "Search"}
          disabled={busy || value.trim().length < 2}
        />
      </form>
    </SearchVisuals>
  );
}
