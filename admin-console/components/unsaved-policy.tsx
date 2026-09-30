"use client";
import { createContext, useCallback, useContext, useEffect, useRef, type ReactNode } from "react";
const Context = createContext<{
  track: (id: string, dirty: boolean) => void;
  leave: () => boolean;
}>({ track: () => {}, leave: () => true });
export function UnsavedPolicies({ children }: { children: ReactNode }) {
  const dirty = useRef(new Set<string>());
  const track = useCallback((id: string, changed: boolean) => {
    if (changed) dirty.current.add(id);
    else dirty.current.delete(id);
  }, []);
  const leave = useCallback(() => {
    if (!dirty.current.size) return true;
    if (!window.confirm("You have unsaved policy changes. Discard them and leave?")) return false;
    dirty.current.clear();
    return true;
  }, []);
  useEffect(() => {
    const unload = (e: BeforeUnloadEvent) => {
      if (dirty.current.size) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    const click = (e: MouseEvent) => {
      const anchor = (e.target as Element).closest("a[href]") as HTMLAnchorElement | null;
      if (
        !anchor ||
        anchor.target === "_blank" ||
        e.metaKey ||
        e.ctrlKey ||
        e.shiftKey ||
        e.altKey ||
        anchor.hash === "#main"
      )
        return;
      if (!leave()) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    // Native traversals include Back/Forward; Link clicks are caught before Next handles them.
    const navigation = (window as Window & { navigation?: EventTarget }).navigation;
    const navigate = (e: Event) => {
      if (e.cancelable && !leave()) e.preventDefault();
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", click, true);
    navigation?.addEventListener("navigate", navigate);
    return () => {
      window.removeEventListener("beforeunload", unload);
      document.removeEventListener("click", click, true);
      navigation?.removeEventListener("navigate", navigate);
    };
  }, [leave]);
  return <Context.Provider value={{ track, leave }}>{children}</Context.Provider>;
}
export function useUnsavedPolicy(id: string, dirty: boolean) {
  const { track } = useContext(Context);
  useEffect(() => {
    track(id, dirty);
    return () => track(id, false);
  }, [id, dirty, track]);
}
export function usePolicyNavigation() {
  return useContext(Context).leave;
}
