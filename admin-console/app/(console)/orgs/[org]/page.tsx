import { Organisation } from "@/components/organisation";
export default async function Page({
  params,
}: {
  params: Promise<{
    org: string;
  }>;
}) {
  return <Organisation org={decodeURIComponent((await params).org)} />;
}
