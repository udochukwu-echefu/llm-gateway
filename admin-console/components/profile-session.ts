/* Full navigation discards the previous scope's document and client caches. */
import { browserSessionApi } from "@/lib/browser-api";
import type { DemoProfile } from "./profile-identity";

export async function switchDemoProfile(profile: DemoProfile) {
  await browserSessionApi("/api/auth/demo", {
    method: "POST",
    body: JSON.stringify({ as: profile }),
  });
}

export async function signOutProfile() {
  await browserSessionApi("/api/auth/logout", { method: "POST" });
}

export function navigateProfileDocument(destination: "/overview" | "/login") {
  window.location.assign(destination);
}
