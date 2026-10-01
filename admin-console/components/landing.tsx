"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { usePreferences } from "./preferences";
export function Landing() {
  const router = useRouter();
  const { value, ready } = usePreferences();
  useEffect(() => {
    if (ready) router.replace(value.landing);
  }, [router, value.landing, ready]);
  return <p>Opening your preferred page…</p>;
}
