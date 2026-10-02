"use client";
import { Select } from "./select";
import { SortableTable } from "./sortable-table";
import {
  actions,
  detectors,
  detectorDescriptions,
  type GuardrailView,
} from "@/lib/policy-contracts";
import { guardrailChanges, noEffect, weakensGuardrails } from "@/lib/policy-changes";
import { usePolicyEditor } from "./use-policy-editor";
import { PolicyEditorFrame } from "./policy-editor-frame";
export function GuardrailsEditor({
  path,
  initial,
  org,
  team,
}: {
  path: string;
  initial: GuardrailView;
  org: string;
  team?: string;
}) {
  const own = (view: GuardrailView) => view.overrides[team ? "team" : "organization"];
  const editor = usePolicyEditor(path, initial, own, (view, draft) =>
    guardrailChanges(own(view), draft),
  );
  return (
    <PolicyEditorFrame
      {...editor}
      title="Guardrails"
      level={team ? `team ${team}` : `organisation ${org}`}
      explanation="The strictest action wins: allow < redact < block. Built-in defaults are a floor."
      danger={
        weakensGuardrails(own(editor.view), editor.draft)
          ? "This removes or weakens a saved guardrail override. Sensitive data may be allowed or redacted where it was previously blocked. Defaults and inherited restrictions still apply."
          : undefined
      }
      save={async (clear) => {
        await editor.save(
          clear
            ? null
            : {
                actions: detectors
                  .filter((d) => editor.draft[d])
                  .map((d) => `${d}=${editor.draft[d]}`),
              },
        );
      }}
    >
      <p className="muted">
        Pattern checks cover recognized text only; they do not inspect images, audio, files or
        obfuscated values.
      </p>
      <SortableTable name="guardrails-editor-1">
        <thead>
          <tr>
            <th>Detector</th>
            <th>Default</th>
            <th>Organisation</th>
            {team && <th>Team</th>}
            <th>This level</th>
            <th>Effective</th>
          </tr>
        </thead>
        <tbody>
          {detectors.map((detector) => (
            <tr key={detector}>
              <th scope="row">
                {detector}
                <small>{detectorDescriptions[detector]}</small>
              </th>
              <td>{editor.view.defaults[detector]}</td>
              <td>{editor.view.overrides.organization[detector] ?? "inherit"}</td>
              {team && <td>{editor.view.overrides.team[detector] ?? "inherit"}</td>}
              <td>
                <Select
                  aria-label={`${detector} action`}
                  value={editor.draft[detector] ?? "inherit"}
                  onValueChange={(value) => {
                    const next = { ...editor.draft };
                    if (value === "inherit") delete next[detector];
                    else next[detector] = value as (typeof actions)[number];
                    editor.setDraft(next);
                  }}
                >
                  <option value="inherit">Inherit</option>
                  {actions.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </Select>
                <small role="status">
                  {noEffect(
                    detector,
                    editor.draft[detector],
                    editor.view.defaults,
                    team ? editor.view.overrides.organization : undefined,
                  )}
                </small>
              </td>
              <td>
                <strong>{editor.view.effective[detector]}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </SortableTable>
    </PolicyEditorFrame>
  );
}
