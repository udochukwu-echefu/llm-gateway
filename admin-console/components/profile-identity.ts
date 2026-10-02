import type { Identity } from "@/lib/contracts";

export interface DemoAvailability {
  enabled: boolean;
  org: boolean;
}
export type DemoProfile = "platform" | "org";
export const noDemoProfiles: DemoAvailability = { enabled: false, org: false };

export function profileIdentity(identity: Identity, demo: DemoAvailability) {
  const current: DemoProfile | null =
    demo.enabled && identity.role === "viewer"
      ? identity.organization?.name === "Northwind Health"
        ? "org"
        : !identity.organization
          ? "platform"
          : null
      : null;
  const title = current
    ? current === "platform"
      ? "Platform viewer"
      : "Northwind Health viewer"
    : identity.name;
  return {
    current,
    title,
    initials: title
      .split(/\s+/)
      .slice(0, 2)
      .map((word) => word[0])
      .join("")
      .toUpperCase(),
    context: `${identity.organization?.name ?? "All organisations"} · ${identity.role === "viewer" ? "Read-only" : identity.role === "platform" ? "Platform admin" : "Organisation admin"}`,
  };
}
