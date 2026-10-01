"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  defaultPreferences,
  readPreferences,
  savePreferences,
  type Preferences,
} from "@/lib/preferences";
const Context = createContext({
  value: defaultPreferences,
  update: (change: Partial<Preferences>) => {
    void change;
  },
  ready: false,
});
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [value, setValue] = useState(defaultPreferences);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const loaded = readPreferences(localStorage);
    queueMicrotask(() => {
      setValue(loaded);
      setReady(true);
    });
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = value.theme;
    document.documentElement.dataset.density = value.density;
  }, [value]);
  function update(change: Partial<Preferences>) {
    const next = { ...value, ...change };
    setValue(next);
    try {
      savePreferences(localStorage, next);
    } catch {
      /* Browser storage may be disabled; current-document preferences still work. */
    }
  }
  return <Context.Provider value={{ value, update, ready }}>{children}</Context.Provider>;
}
export function usePreferences() {
  return useContext(Context);
}
