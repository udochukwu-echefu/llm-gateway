"use client";
import type { Catalog, ListPolicy } from "@/lib/policy-contracts";
import { listChanges } from "@/lib/policy-changes";
import { regions as regionNames, regionDescriptions } from "@/lib/policy-contracts";
import { usePolicyEditor } from "./use-policy-editor";
import { PolicyEditorFrame } from "./policy-editor-frame";
import { PolicyLevelChoice, type ListMode } from "./policy-level-choice";
import { EffectiveModelsView, OverrideList } from "./policy-effective";
export function ListPolicyEditor({
  kind,
  path,
  initial,
  org,
  team,
  catalog,
}: {
  kind: "model-policy" | "residency";
  path: string;
  initial: ListPolicy;
  org: string;
  team?: string;
  catalog: Catalog;
}) {
  const isRegions = kind === "residency";
  const title = isRegions ? "Residency" : "Model policy";
  const own = (view: ListPolicy) => view.overrides[team ? "team" : "organization"];
  const draftOf = (view: ListPolicy) => {
    const values = own(view);
    return {
      values,
      mode: (values === null ? "inherit" : values.length ? "only" : "nothing") as ListMode,
    };
  };
  const editor = usePolicyEditor(path, initial, draftOf, (view, draft) =>
    listChanges(own(view), draft.values),
  );
  const mode = editor.draft.mode;
  function choose(next: ListMode) {
    editor.setDraft({ mode: next, values: next === "inherit" ? null : [] });
  }
  function toggle(value: string, checked: boolean) {
    editor.setDraft((current) => ({
      ...current,
      values: checked
        ? [...(current.values ?? []), value]
        : (current.values ?? []).filter((v) => v !== value),
    }));
  }
  const providers = [...new Set(catalog.models.map((model) => model.provider))];
  const level = team ? `team ${team}` : `organisation ${org}`;
  return (
    <PolicyEditorFrame
      {...editor}
      title={title}
      level={level}
      explanation={
        isRegions
          ? "Both region lists must allow a model's processing region."
          : "Both lists must allow a model. Organisation and team policies intersect."
      }
      reload={async () => {
        await editor.reload();
      }}
      valid={mode !== "only" || Boolean(editor.draft.values?.length)}
      danger={
        editor.draft.values === null
          ? `Remove the restriction for ${level}? Inherited restrictions still apply.`
          : mode === "nothing"
            ? `This blocks every model for ${level}. Applications will be refused until access is restored.`
            : undefined
      }
      save={async (clear) => {
        await editor.save(
          clear || editor.draft.values === null
            ? null
            : { [isRegions ? "regions" : "allow"]: editor.draft.values },
        );
      }}
    >
      <div className="policy-comparison">
        <OverrideList title="Organisation override" values={editor.view.overrides.organization} />
        {team && <OverrideList title="Team override" values={editor.view.overrides.team} />}
        <div>
          <h3>Effective result</h3>
          {isRegions && <p>Regions: {editor.view.effective.regions?.join(", ") || "No regions"}</p>}
          <EffectiveModelsView effective={editor.view.effective} />
        </div>
      </div>
      <PolicyLevelChoice
        title={`${title} at this level`}
        mode={mode}
        onChange={choose}
        regions={isRegions}
      />
      {mode === "only" && (
        <div className="policy-options">
          {isRegions
            ? regionNames.map((region) => (
                <label className="check" key={region}>
                  <input
                    type="checkbox"
                    checked={editor.draft.values?.includes(region) ?? false}
                    onChange={(e) => toggle(region, e.target.checked)}
                  />
                  <span>
                    {region} <small>{regionDescriptions[region]}</small>
                  </span>
                </label>
              ))
            : providers.map((provider) => (
                <fieldset key={provider}>
                  <legend>{provider}</legend>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={editor.draft.values?.includes(`${provider}/*`) ?? false}
                      onChange={(e) => toggle(`${provider}/*`, e.target.checked)}
                    />
                    Whole provider · {`${provider}/*`}
                  </label>
                  {catalog.models
                    .filter((m) => m.provider === provider)
                    .map((model) => (
                      <label className="check" key={model.name}>
                        <input
                          type="checkbox"
                          checked={editor.draft.values?.includes(model.name) ?? false}
                          onChange={(e) => toggle(model.name, e.target.checked)}
                        />
                        <span>
                          {model.name}
                          <small>
                            {model.region} · {model.endpoints.join(", ")} ·{" "}
                            {model.priced ? "Priced" : "Not currently priced"}
                          </small>
                        </span>
                      </label>
                    ))}
                </fieldset>
              ))}
        </div>
      )}
      {mode === "only" && !editor.draft.values?.length && (
        <p role="alert">
          Choose at least one {isRegions ? "region" : "model or provider"}. Use the explicit{" "}
          {isRegions ? "Allow no regions" : "Allow nothing"} option to block all access.
        </p>
      )}
    </PolicyEditorFrame>
  );
}
