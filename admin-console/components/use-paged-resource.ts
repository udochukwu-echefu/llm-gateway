"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { browserApi } from "@/lib/browser-api";
import type { Page } from "@/lib/contracts";
export function usePagedResource<T>(path: string) {
  const [data, setData] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const load = useCallback(
    async (after?: string) => {
      const version = generation.current;
      setLoading(true);
      setError("");
      try {
        const page = await browserApi<Page<T> & { total?: number }>(
          path +
            (after ? `${path.includes("?") ? "&" : "?"}cursor=${encodeURIComponent(after)}` : ""),
        );
        if (version !== generation.current) return;
        setData((old) => (after ? [...old, ...page.data] : page.data));
        setTotal(page.total ?? page.data.length);
        setCursor(page.next_cursor == null ? null : String(page.next_cursor));
      } catch (error) {
        if (version === generation.current) setError((error as Error).message);
      } finally {
        if (version === generation.current) setLoading(false);
      }
    },
    [path],
  );
  useEffect(() => {
    const counter = generation;
    counter.current++;
    queueMicrotask(() => {
      setData([]);
      void load();
    });
    return () => {
      counter.current++;
    };
  }, [load]);
  return {
    data,
    total,
    cursor,
    loading,
    error,
    refresh: () => load(),
    more: () => cursor && load(cursor),
  };
}
