import { redirect } from "next/navigation";
import { Settings } from "@/components/settings";
import { readSession } from "@/lib/session";
import { isActive } from "@/lib/session-policy";
export default async function Page() {
  const session = await readSession();
  if (!isActive(session)) redirect("/login");
  return (
    <Settings
      identity={session.identity!}
      issuedAt={session.issuedAt!}
      lastSeen={session.lastSeen!}
      demo={session.demo === true}
    />
  );
}
