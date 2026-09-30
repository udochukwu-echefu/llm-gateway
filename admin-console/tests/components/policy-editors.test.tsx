import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, afterEach, expect, test, vi } from "vitest";
import { ListPolicyEditor } from "@/components/list-policy-editor";
import { GuardrailsEditor } from "@/components/guardrails-editor";
import { CachePurge } from "@/components/cache-purge";
import { UnsavedPolicies } from "@/components/unsaved-policy";
import type { ListPolicy, GuardrailView } from "@/lib/policy-contracts";
const version = "a".repeat(64);
const initial: ListPolicy = {
  version,
  overrides: { organization: null, team: null },
  effective: { models: ["groq/openai/gpt-oss-20b"], aliases: [] },
};
const catalog = {
  models: [
    {
      name: "groq/openai/gpt-oss-20b",
      provider: "groq",
      region: "unknown",
      endpoints: ["chat"],
      priced: true,
    },
  ],
  aliases: {},
};
const defaults = {
  secret_api_key: "block",
  secret_private_key: "block",
  email: "allow",
  phone: "allow",
  card_number: "redact",
  iban: "redact",
  ip_address: "allow",
} as const;
const guardrails: GuardrailView = {
  version,
  defaults,
  overrides: { organization: { email: "block" }, team: {} },
  effective: { ...defaults, email: "block" },
};
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
});
afterEach(() => vi.unstubAllGlobals());
function list(kind: "model-policy" | "residency" = "model-policy") {
  return (
    <ListPolicyEditor
      kind={kind}
      path={`/api/admin/orgs/Fake/${kind}`}
      initial={initial}
      org="Fake"
      catalog={catalog}
    />
  );
}
for (const kind of ["model-policy", "residency"] as const)
  test(`${kind} deny-all requires confirmation before a conditional write`, async () => {
    const user = userEvent.setup();
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response('{"updated":true}'))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...initial,
            version: "b".repeat(64),
            overrides: { organization: [], team: null },
            effective: { models: [], aliases: [] },
          }),
        ),
      );
    vi.stubGlobal("fetch", fetch);
    render(list(kind));
    expect(screen.queryByRole("button", { name: /^Save/ })).toBeNull();
    await user.click(
      screen.getByLabelText(kind === "residency" ? "Allow no regions" : "Allow nothing"),
    );
    await user.click(screen.getByRole("button", { name: /^Save/ }));
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog").textContent).toContain("blocks every model");
    await user.click(screen.getByText("Confirm change"));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls[0][1].headers["If-Match"]).toBe(`"${version}"`);
  });
test("weakening a guardrail requires confirmation", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(
    <GuardrailsEditor path="/api/admin/orgs/Fake/guardrails" initial={guardrails} org="Fake" />,
  );
  await user.selectOptions(screen.getByLabelText("email action"), "redact");
  await user.click(screen.getByText("Save guardrails"));
  expect(screen.getByRole("dialog").textContent).toContain("weakens a saved guardrail");
  expect(fetch).not.toHaveBeenCalled();
});
test("purge requires the exact typed name before calling the BFF", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn().mockResolvedValue(new Response('{"purged":7}'));
  vi.stubGlobal("fetch", fetch);
  render(<CachePurge org="Fake org" team="Fake team" />);
  await user.click(screen.getByText("Purge cache"));
  const button = screen.getByText("Confirm purge") as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  await user.click(button);
  expect(fetch).not.toHaveBeenCalled();
  await user.type(screen.getByLabelText("Type Fake team to confirm"), "fake team");
  expect(button.disabled).toBe(true);
  await user.clear(screen.getByRole("textbox"));
  await user.type(screen.getByRole("textbox"), "Fake team");
  expect(button.disabled).toBe(false);
  await user.click(button);
  await screen.findByText("Purged 7 cached responses.");
});
test("conflict keeps the draft and never automatically retries", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn().mockResolvedValue(new Response('{"error":"Conflict"}', { status: 412 }));
  vi.stubGlobal("fetch", fetch);
  render(list());
  await user.click(screen.getByLabelText("Allow only these", { exact: true }));
  const checkbox = screen.getByLabelText("Whole provider · groq/*") as HTMLInputElement;
  await user.click(checkbox);
  await user.click(screen.getByText("Save model policy"));
  await screen.findByText("Someone else changed this policy. Reload to see their version");
  expect(checkbox.checked).toBe(true);
  expect(fetch).toHaveBeenCalledOnce();
  expect((screen.getByText("Save model policy") as HTMLButtonElement).disabled).toBe(true);
});
test("removing an override names the level and reload resets the mode", async () => {
  const user = userEvent.setup();
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(
        JSON.stringify({ ...initial, overrides: { organization: ["groq/*"], team: null } }),
      ),
    );
  vi.stubGlobal("fetch", fetch);
  render(list());
  await user.click(screen.getByText("Remove override"));
  expect(screen.getByRole("dialog").textContent).toContain("organisation Fake");
  fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
  await user.click(screen.getByText("Reload model policy"));
  await waitFor(() =>
    expect(
      (screen.getByLabelText("Allow only these", { exact: true }) as HTMLInputElement).checked,
    ).toBe(true),
  );
});
test("503 purge explains Redis availability without claiming success", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response('{"error":"Cache unavailable"}', { status: 503 })),
  );
  render(<CachePurge org="Fake" />);
  await user.click(screen.getByText("Purge cache"));
  await user.type(screen.getByRole("textbox"), "Fake");
  await user.click(screen.getByText("Confirm purge"));
  await screen.findAllByText(/Redis is unavailable/);
  expect(screen.queryByText(/^Purged/)).toBeNull();
});
test("unsaved policy edits warn before page navigation and retain edits when cancelled", async () => {
  const user = userEvent.setup();
  const confirm = vi.fn().mockReturnValue(false);
  vi.stubGlobal("confirm", confirm);
  render(
    <UnsavedPolicies>
      {list()}
      <a href="/audit">Leave</a>
    </UnsavedPolicies>,
  );
  await user.click(screen.getByLabelText("Allow nothing"));
  await user.click(screen.getByText("Leave"));
  expect(confirm).toHaveBeenCalledOnce();
  expect((screen.getByLabelText("Allow nothing") as HTMLInputElement).checked).toBe(true);
});
