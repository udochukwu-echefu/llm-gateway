"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { updateQuery } from "@/lib/list-query";
export function useListQuery() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  return {
    params,
    set: (change: Record<string, string | null>) =>
      router.push(pathname + "?" + updateQuery(params.toString(), change), { scroll: false }),
  };
}
