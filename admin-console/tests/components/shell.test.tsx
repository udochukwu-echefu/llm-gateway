import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Settings } from "@/components/settings";
import { Shell } from "@/components/shell";

vi.mock("next/navigation", () => ({ usePathname: () => "/overview" }));
vi.mock("@/components/global-commands", () => ({ GlobalCommands: () => null }));
vi.mock("@/components/breadcrumbs", () => ({ Breadcrumbs: () => null }));
vi.mock("@/components/use-resource", () => ({ useResource: () => ({ loading: false, data: {} }) }));

for (const role of ["platform", "org", "viewer"] as const) {
  test(`${role} account keeps the full name accessible outside the sidebar`, async () => {
    const name = "Long identity " + "WithoutSpaces".repeat(8);

    render(
      <Shell identity={{ key_id: "fake-id", name, role, organization: null }}>
        <Settings
          identity={{ key_id: "fake-id", name, role, organization: null }}
          issuedAt={Date.now()}
          lastSeen={Date.now()}
        />
      </Shell>,
    );

    const displayed = await screen.findByText(name);
    expect(displayed.getAttribute("title")).toBe(name);
    expect(displayed.className).toBe("identity-name");
    expect(displayed.closest(".settings-panel")).not.toBeNull();
    expect(document.querySelector(".sidebar-footer .identity-name")).toBeNull();
  });
}
