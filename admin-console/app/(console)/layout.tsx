import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Shell } from "@/components/shell";
import type { Identity } from "@/lib/contracts";
import { readConfig } from "@/lib/config";
export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const identity = (await headers()).get("x-console-identity");
  if (!identity) redirect("/login");
  const config = readConfig();
  return (
    <Shell
      identity={JSON.parse(identity) as Identity}
      demo={{ enabled: config.DEMO_MODE, org: config.DEMO_MODE && !!config.DEMO_ORG_VIEWER_KEY }}
    >
      {children}
    </Shell>
  );
}
