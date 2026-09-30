import { headers } from "next/headers";
import type { Identity } from "@/lib/contracts";
import { AuditLog } from "@/components/audit-log";
export default async function Page() {
  const identity = JSON.parse((await headers()).get("x-console-identity")!) as Identity;
  return <AuditLog platform={identity.role === "platform"} />;
}
