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
  const animation = useRef<Animation | null>(null);
  useEffect(
    () => () => {
      animation.current?.cancel();
      transition.current?.skipTransition();
      document.documentElement.classList.remove("theme-reveal");
    },
    [],
  );

  function toggle(event: React.MouseEvent<HTMLButtonElement>) {
    if (transition.current) return;
    const update = () => flushSync(() => preferences.update({ theme: dark ? "light" : "dark" }));
    if (
      !document.startViewTransition ||
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      update();
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const radius = Math.ceil(
      Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y)) * 1.02,
    );
    document.documentElement.classList.add("theme-reveal");
    let current: ViewTransition;
    try {
      current = document.startViewTransition(update);
    } catch {
      document.documentElement.classList.remove("theme-reveal");
      update();
      return;
    }
    transition.current = current;
    void current.ready
      .then(() => {
        animation.current = document.documentElement.animate(
          { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
          {
            duration: 450,
            easing: "ease-in-out",
            fill: "forwards",
            pseudoElement: "::view-transition-new(root)",
          },
        );
      })
      .catch(() => current.skipTransition());
    void current.finished
      .catch(() => {})
      .finally(() => {
        if (transition.current !== current) return;
        animation.current?.cancel();
        animation.current = null;
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
      <span className="theme-toggle-gloss" aria-hidden="true" />
      <span
        className={
          dark ? "theme-toggle-icon theme-toggle-sun" : "theme-toggle-icon theme-toggle-moon"
        }
        aria-hidden="true"
      />
    </button>
  );
}
