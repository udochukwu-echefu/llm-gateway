"use client";
import { useCallback, useEffect, useState } from "react";
import { browserApi } from "@/lib/browser-api";
export function useResource<T>(path: string) {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<{
    path: string;
    version: number;
    data?: T;
    error?: string;
    loadedAt?: number;
  }>();
  useEffect(() => {
    let active = true;
    browserApi<T>(path)
      .then((data) => {
        if (active) setResult({ path, version, data, loadedAt: Date.now() });
      })
      .catch((error: Error) => {
        if (active) setResult({ path, version, error: error.message });
      });
    return () => {
      active = false;
    };
  }, [path, version]);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  const current = result?.path === path && result.version === version ? result : undefined;
  return {
    data: current?.data,
    error: current?.error,
    loading: !current,
    refresh,
    loadedAt: current?.loadedAt,
  };
}
