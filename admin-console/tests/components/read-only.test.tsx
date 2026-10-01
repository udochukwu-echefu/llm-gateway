import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ReadOnlyProvider, READ_ONLY_REASON } from "@/components/read-only";
import { MutationForm } from "@/components/mutation-form";
import { CachePurge } from "@/components/cache-purge";
import { PolicyEditorFrame } from "@/components/policy-editor-frame";

test("viewer controls stay visible disabled with an explanation", () => {
  render(
    <ReadOnlyProvider viewer>
      <MutationForm
        path="/orgs"
        fields={[{ name: "name", label: "Organisation name" }]}
        label="Create organisation"
        onSuccess={vi.fn()}
      />
      <CachePurge org="Fake" />
      <PolicyEditorFrame
        title="Model policy"
        level="Fake"
        explanation="Models"
        changes={[]}
        error=""
        conflict={false}
        needsReload={false}
        busy={false}
        notice=""
        reload={vi.fn()}
        save={vi.fn()}
      >
        <input aria-label="Policy setting" />
      </PolicyEditorFrame>
    </ReadOnlyProvider>,
  );
  for (const name of ["Create organisation", "Purge cache", "Remove override", "Save model policy"])
    expect(screen.getByRole("button", { name })).toHaveProperty("disabled", true);
  expect(screen.getByLabelText("Organisation name")).toHaveProperty("disabled", true);
  expect(screen.getByLabelText("Policy setting").closest("fieldset")).toHaveProperty(
    "disabled",
    true,
  );
  expect(screen.getAllByText(READ_ONLY_REASON).length).toBe(3);
  expect(screen.getByRole("button", { name: "Reload model policy" })).toHaveProperty(
    "disabled",
    false,
  );
});
