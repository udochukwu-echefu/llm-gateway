import { headers } from "next/headers";
import { redirect } from "next/navigation";
import type { Identity } from "@/lib/contracts";
import { Organisations } from "@/components/organisations";
export default async function Page() {
  const identity = JSON.parse((await headers()).get("x-console-identity")!) as Identity;
  if (identity.organization) redirect(`/orgs/${encodeURIComponent(identity.organization.name)}`);
  return <Organisations />;
}
