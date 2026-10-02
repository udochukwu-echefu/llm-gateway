"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export function useProfileDisclosure() {
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [state, setState] = useState<"closed" | "preview" | "pinned">("closed");
  const clearTimer = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }, []);
  const close = useCallback(() => {
    clearTimer();
    setState("closed");
  }, [clearTimer]);
  useEffect(() => {
    if (state === "closed") return;
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target)) close();
    }
    function escape(event: KeyboardEvent) {
      if (event.key !== "Escape" || document.querySelector("dialog[open]")) return;
      event.preventDefault();
      close();
      trigger.current?.focus();
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [state, close]);
  useEffect(() => clearTimer, [clearTimer]);
  return {
    root,
    trigger,
    close,
    open: state !== "closed",
    toggle() {
      clearTimer();
      setState((value) => (value === "pinned" ? "closed" : "pinned"));
    },
    preview(pointerType: string) {
      if (pointerType !== "mouse" || document.querySelector("dialog[open]")) return;
      clearTimer();
      setState((value) => (value === "closed" ? "preview" : value));
    },
    leave() {
      if (state !== "preview") return;
      clearTimer();
      timer.current = setTimeout(close, 200);
    },
    pin() {
      clearTimer();
      setState((value) => (value === "closed" ? value : "pinned"));
    },
  };
}
