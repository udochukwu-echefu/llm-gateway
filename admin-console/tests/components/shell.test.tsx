import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Shell } from "@/components/shell";

vi.mock("next/navigation", () => ({ usePathname: () => "/overview" }));
vi.mock("@/components/global-commands", () => ({ GlobalCommands: () => null }));
vi.mock("@/components/breadcrumbs", () => ({ Breadcrumbs: () => null }));

for (const role of ["platform", "org", "viewer"] as const) {
  test(`${role} sidebar identity keeps the full name accessible`, async () => {
    const name = "Long identity " + "WithoutSpaces".repeat(8);

    render(
      <Shell identity={{ key_id: "fake-id", name, role, organization: null }}>
        <h1>Overview</h1>
      </Shell>,
    );

    const displayed = await screen.findByText(name);
    expect(displayed.getAttribute("title")).toBe(name);
    expect(displayed.className).toBe("identity-name");
    expect(displayed.closest(".sidebar-footer")).not.toBeNull();
  });
}
