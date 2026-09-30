import { Team } from "@/components/team";
export default async function Page({
  params,
}: {
  params: Promise<{
    org: string;
    team: string;
  }>;
}) {
  const { org, team } = await params;
  return <Team org={decodeURIComponent(org)} team={decodeURIComponent(team)} />;
}
