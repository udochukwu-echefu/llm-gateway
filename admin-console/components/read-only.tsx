"use client";
import { createContext, useContext, type ReactNode } from "react";

export const READ_ONLY_REASON = "Read-only demo. Changes are disabled.";
const ReadOnly = createContext(false);
export function ReadOnlyProvider({ viewer, children }: { viewer: boolean; children: ReactNode }) {
  return <ReadOnly.Provider value={viewer}>{children}</ReadOnly.Provider>;
}
export function useReadOnly() {
  return useContext(ReadOnly);
}
export function ReadOnlyNotice() {
  return useReadOnly() ? <p className="muted">{READ_ONLY_REASON}</p> : null;
}
