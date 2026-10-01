import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { FilterBar, SortHeading } from "@/components/list-controls";
const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  params: "status=5xx&org=Fake",
  pathname: "/requests",
}));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.params),
  usePathname: () => navigation.pathname,
  useRouter: () => ({ push: navigation.push }),
}));
test("URL-synced filter form and chips preserve scope and browser history navigation", async () => {
  const user = userEvent.setup();
  render(
    <FilterBar
      fields={[
        { name: "status", label: "Status" },
        { name: "team", label: "Team" },
      ]}
    />,
  );
  expect((screen.getByLabelText("Status") as HTMLInputElement).value).toBe("5xx");
  await user.type(screen.getByLabelText("Team"), "Search");
  await user.click(screen.getByRole("button", { name: "Apply filters" }));
  expect(navigation.push).toHaveBeenCalledWith("/requests?status=5xx&org=Fake&team=Search", {
    scroll: false,
  });
  await user.click(screen.getByRole("button", { name: "Status: 5xx ×" }));
  expect(navigation.push).toHaveBeenLastCalledWith("/requests?org=Fake", { scroll: false });
});
test("sortable heading records sort direction in the shareable URL", async () => {
  const user = userEvent.setup();
  render(
    <table>
      <thead>
        <tr>
          <SortHeading field="duration_ms">Duration</SortHeading>
        </tr>
      </thead>
    </table>,
  );
  await user.click(screen.getByRole("button", { name: /Duration/ }));
  expect(navigation.push).toHaveBeenLastCalledWith(
    "/requests?status=5xx&org=Fake&sort=duration_ms&direction=asc",
    { scroll: false },
  );
});
