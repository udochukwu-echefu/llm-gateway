import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Shell } from "@/components/shell";
import type { Identity } from "@/lib/contracts";
export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const identity = (await headers()).get("x-console-identity");
  if (!identity) redirect("/login");
  return <Shell identity={JSON.parse(identity) as Identity}>{children}</Shell>;
}
