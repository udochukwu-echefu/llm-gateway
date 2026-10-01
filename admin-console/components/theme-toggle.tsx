"use client";
import { useEffect, useRef, useSyncExternalStore } from "react";
import { flushSync } from "react-dom";
import { usePreferences } from "./preferences";

function subscribeToAppearance(onChange: () => void) {
  if (!window.matchMedia) return () => {};
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}
function prefersDark() {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function ThemeToggle() {
  const preferences = usePreferences();
  const systemDark = useSyncExternalStore(subscribeToAppearance, prefersDark, () => false);
  const dark =
    preferences.value.theme === "dark" || (preferences.value.theme === "system" && systemDark);
  const transition = useRef<ViewTransition | null>(null);
  useEffect(
    () => () => {
      transition.current?.skipTransition();
      document.documentElement.classList.remove("theme-reveal");
    },
    [],
  );

  function toggle(event: React.MouseEvent<HTMLButtonElement>) {
    const update = () => flushSync(() => preferences.update({ theme: dark ? "light" : "dark" }));
    transition.current?.skipTransition();
    if (
      !document.startViewTransition ||
      event.detail === 0 ||
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      document.documentElement.classList.remove("theme-reveal");
      update();
      return;
    }
    document.documentElement.classList.add("theme-reveal");
    const current = document.startViewTransition(update);
    transition.current = current;
    void current.finished
      .catch(() => {})
      .finally(() => {
        if (transition.current !== current) return;
        transition.current = null;
        document.documentElement.classList.remove("theme-reveal");
      });
  }

  return (
    <button
      type="button"
      className={`theme-toggle${dark ? " theme-toggle-dark" : ""}`}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      title={dark ? "Switch to light theme" : "Switch to dark theme"}
      disabled={!preferences.ready}
      onClick={toggle}
    >
      <span className="theme-toggle-sun" aria-hidden="true" />
      <span className="theme-toggle-moon" aria-hidden="true" />
    </button>
  );
}
