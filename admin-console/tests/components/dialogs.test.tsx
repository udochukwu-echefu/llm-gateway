import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, expect, test, vi } from "vitest";
import { KeyCreatedDialog } from "@/components/key-created-dialog";
import { RevokeDialog } from "@/components/revoke-dialog";
import { MutationForm } from "@/components/mutation-form";
import { TeamKeys } from "@/components/team-keys";
vi.mock("@/components/use-list-query", () => ({
  useListQuery: () => ({ params: new URLSearchParams(), set: vi.fn() }),
}));
vi.mock("@/components/use-paged-resource", () => ({
  usePagedResource: () => ({
    data: [],
    total: 0,
    cursor: null,
    loading: false,
    error: "",
    refresh: vi.fn(),
    more: vi.fn(),
  }),
}));
vi.mock("@/components/use-resource", () => ({
  useResource: () => ({ data: { data: [], next_cursor: null }, loading: false, refresh: vi.fn() }),
}));
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
});
test("created key warning and close callback on Escape", () => {
  const close = vi.fn();
  render(<KeyCreatedDialog secret="obviously-fake-key" onClose={close} />);
  expect(screen.getByText(/You won’t see this again/)).toBeDefined();
  fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
  expect(close).toHaveBeenCalledOnce();
});
test("the created key cannot be reopened after closing", async () => {
  const user = userEvent.setup();
  const secret = "lgw_abcdefghijkl_" + "x".repeat(43);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ key: secret }))));
  render(<TeamKeys base="/orgs/fake/teams/test" orgBase="/orgs/fake" team="test" />);
  await user.type(screen.getByLabelText("Key name"), "fake-app");
  await user.click(screen.getByText("Create API key"));
  await screen.findByText(secret);
  await user.click(screen.getByText("I saved the key"));
  expect(screen.queryByText(secret)).toBeNull();
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.queryByRole("button", { name: /reveal|show key|reopen/i })).toBeNull();
  vi.unstubAllGlobals();
});
test("revoke requires explicit confirmation naming the key ID", async () => {
  const user = userEvent.setup();
  const confirm = vi.fn().mockResolvedValue(undefined);
  render(<RevokeDialog keyId="fakepublicid" onClose={vi.fn()} onConfirm={confirm} />);
  const button = screen.getByText("Confirm revoke") as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  await user.click(button);
  expect(confirm).not.toHaveBeenCalled();
  await user.click(screen.getByRole("checkbox"));
  await user.click(button);
  await waitFor(() => expect(confirm).toHaveBeenCalledOnce());
});
test("invalid form never calls the BFF", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(
    <MutationForm
      path="/orgs/fake/teams/test/limits"
      method="PUT"
      label="Save"
      fields={[
        { name: "rpm", label: "RPM", type: "integer" },
        { name: "tpm", label: "TPM", type: "integer" },
        { name: "max_concurrency", label: "Concurrency", type: "integer" },
      ]}
      onSuccess={vi.fn()}
    />,
  );
  await user.type(screen.getByLabelText("RPM"), "-1");
  await user.click(screen.getByText("Save"));
  expect(screen.getByRole("alert")).toBeDefined();
  expect(fetch).not.toHaveBeenCalled();
  vi.unstubAllGlobals();
});
test("creation retry retains its submission ID and editing starts a new submission", async () => {
  const user = userEvent.setup();
  const fetch = vi
    .fn()
    .mockRejectedValueOnce(new Error("Fake offline failure"))
    .mockResolvedValue(new Response(JSON.stringify({ id: "fake-resource" })));
  vi.stubGlobal("fetch", fetch);
  render(
    <MutationForm
      path="/orgs"
      label="Create"
      fields={[{ name: "name", label: "Name" }]}
      onSuccess={vi.fn()}
    />,
  );
  await user.type(screen.getByLabelText("Name"), "Fake org");
  await user.click(screen.getByText("Create"));
  await screen.findByText("Fake offline failure");
  const first = fetch.mock.calls[0][1].headers["Idempotency-Key"];
  await user.click(screen.getByText("Create"));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  expect(fetch.mock.calls[1][1].headers["Idempotency-Key"]).toBe(first);
  await user.type(screen.getByLabelText("Name"), "Another fake org");
  fetch.mockResolvedValueOnce(new Response(JSON.stringify({ id: "fake-resource-2" })));
  await user.click(screen.getByText("Create"));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
  expect(fetch.mock.calls[2][1].headers["Idempotency-Key"]).not.toBe(first);
  vi.unstubAllGlobals();
});
