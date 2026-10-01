"use client";
import { useEffect, useState } from "react";
import { absoluteTime, relativeTime } from "@/lib/relative-time";
import { usePreferences } from "./preferences";
export function RecordTime({ value }: { value: string | null | undefined }) {
  const { value: preferences } = usePreferences();
  const [now, setNow] = useState<number>();
  useEffect(() => {
    queueMicrotask(() => setNow(Date.now()));
    const timer = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(timer);
  }, []);
  if (!value) return <span>Never</span>;
  return (
    <time dateTime={value} title={absoluteTime(value, preferences.time)}>
      {now ? relativeTime(value, now) : absoluteTime(value, preferences.time)}{" "}
      <small>
        {preferences.time === "utc" ? "UTC" : Intl.DateTimeFormat().resolvedOptions().timeZone}
      </small>
    </time>
  );
}
