import { afterEach, expect, test, vi } from "vitest";
import { fetchIdentity } from "@/lib/identity";
import type { Identity } from "@/lib/contracts";

afterEach(() => vi.unstubAllGlobals());

for (const organization of [null, { id: "fake-org", name: "Northwind Health" }]) {
  test(`demo ${organization ? "Northwind" : "platform"} identity hides boot metadata without changing authorization`, async () => {
    const internal: Identity = {
      key_id: "fake-boot-id",
      name: "Appliance demo boot synthetic-rotation-id:viewer",
      role: "viewer",
      organization,
    };
    const fetcher = vi.fn().mockImplementation(async () => Response.json(internal));
    vi.stubGlobal("fetch", fetcher);

    const identity = await fetchIdentity("http://fake.test", "fake-key", true);

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledWith("http://fake.test/admin/v1/me", expect.any(Object));
    expect(identity).toEqual({
      ...internal,
      name: organization
        ? "Demo visitor · Northwind Health viewer"
        : "Demo visitor · Platform viewer",
    });
    expect(JSON.stringify(identity)).not.toContain("synthetic-rotation-id");
  });
}

for (const role of ["platform", "org", "viewer"] as const) {
  test(`ordinary ${role} identity retains its full original name`, async () => {
    const internal: Identity = {
      key_id: "fake-id",
      name: "Long operator name " + "WithoutSpaces".repeat(8),
      role,
      organization: role === "org" ? { id: "fake-org", name: "Northwind Health" } : null,
    };
    const fetcher = vi.fn().mockImplementation(async () => Response.json(internal));
    vi.stubGlobal("fetch", fetcher);

    expect(await fetchIdentity("http://fake.test", "fake-key")).toEqual(internal);
    expect(fetcher).toHaveBeenCalledTimes(1);
    if (role !== "viewer") {
      expect(await fetchIdentity("http://fake.test", "fake-key", true)).toEqual(internal);
      expect(fetcher).toHaveBeenCalledTimes(2);
    }
  });
}
