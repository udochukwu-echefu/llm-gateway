"use client";
import { useEffect, useState } from "react";
import { useResource } from "./use-resource";
import { useListQuery } from "./use-list-query";
import { OrgScope, useOrgScope } from "./org-scope";
import { FilterBar, SortHeading, PageCount } from "./list-controls";
import { DataState } from "./data-state";
import { MoneyValue } from "./money-value";
import { allPages } from "@/lib/usage-data";
import { browserApi } from "@/lib/browser-api";
import { listSort } from "@/lib/list-query";
import type { ConsoleModel } from "@/lib/console-contracts";
import type { NamedResource } from "@/lib/contracts";
export function Models() {
  const scope = useOrgScope();
  const { params, set } = useListQuery();
  const catalog = useResource<{
    models: ConsoleModel[];
    aliases: Record<string, { model: string; weight: number }[]>;
  }>("/api/admin/catalog");
  const [permissions, setPermissions] = useState<Record<string, string[]>>({}),
    [error, setError] = useState(""),
    [permissionOrg, setPermissionOrg] = useState<string>();
  useEffect(() => {
    let active = true;
    if (!scope.org) return;
    const base = `/api/admin/orgs/${encodeURIComponent(scope.org)}`;
    allPages<NamedResource>(`${base}/teams`)
      .then((teams) =>
        Promise.all(
          teams.map(async (team) => ({
            team: team.name,
            policy: await browserApi<{ effective: { models: string[] } }>(
              `${base}/model-policy?team=${encodeURIComponent(team.name)}`,
            ),
          })),
        ),
      )
      .then((values) => {
        if (!active) return;
        const result: Record<string, string[]> = {};
        for (const value of values)
          for (const model of value.policy.effective.models)
            (result[model] ??= []).push(value.team);
        setPermissions(result);
        setPermissionOrg(scope.org);
        setError("");
      })
      .catch((error) => {
        if (active) setError((error as Error).message);
      });
    return () => {
      active = false;
    };
  }, [scope.org]);
  const filtered = (catalog.data?.models ?? []).filter(
    (model) =>
      (!params.get("provider") || model.provider === params.get("provider")) &&
      (!params.get("region") || model.region === params.get("region")) &&
      (!params.get("endpoint") || model.endpoints.includes(params.get("endpoint")!)),
  );
  const rows = listSort(
    filtered,
    (params.get("sort") ?? "name") as keyof ConsoleModel,
    params.get("direction") ?? "asc",
  );
  const shown = Number(params.get("shown") ?? 25);
  return (
    <>
      <div className="screen-heading">
        <h1>Models</h1>
        <p>
          Reviewed catalogue. Host identifies who receives the request; maker identifies who built
          the model. Prices are USD per million tokens.
        </p>
      </div>
      <OrgScope {...scope} />
      <section className="panel">
        <FilterBar
          fields={[
            {
              name: "provider",
              label: "Provider",
              options: ["groq", "deepseek", "gemini", "openai", "zai", "nvidia"],
            },
            {
              name: "region",
              label: "Region",
              options: ["us", "eu", "cn", "sg", "global", "unknown"],
            },
            { name: "endpoint", label: "Endpoint", options: ["chat", "embeddings"] },
          ]}
        />
        <DataState {...catalog} />
        {error && <p role="alert">{error}</p>}
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <SortHeading field="name">Model</SortHeading>
                <SortHeading field="provider">Host</SortHeading>
                <SortHeading field="maker">Maker</SortHeading>
                <SortHeading field="region">Region</SortHeading>
                <SortHeading field="endpoints">Endpoints</SortHeading>
                <th>Effective prices / history</th>
                <th>Which teams can use this model?</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, shown).map((model) => (
                <tr key={model.name}>
                  <td>{model.name}</td>
                  <td>{model.provider}</td>
                  <td>{model.maker}</td>
                  <td>
                    {model.region}
                    {model.region_source_url && (
                      <small>
                        <a href={model.region_source_url} target="_blank" rel="noreferrer">
                          Region source
                        </a>{" "}
                        · checked {model.region_checked_on}
                      </small>
                    )}
                  </td>
                  <td>{model.endpoints.join(", ")}</td>
                  <td>
                    {model.effective_price ? (
                      <>
                        <MoneyValue value={model.effective_price.input_price} /> input /{" "}
                        <MoneyValue value={model.effective_price.output_price} /> output /{" "}
                        <MoneyValue value={model.effective_price.cached_input_price} /> cached input
                        <br />
                        <a href={model.effective_price.source_url} target="_blank" rel="noreferrer">
                          Price source
                        </a>{" "}
                        · checked {model.effective_price.checked_on}
                        <details>
                          <summary>Price history</summary>
                          <ul>
                            {model.prices.map((price) => (
                              <li key={price.effective_from}>
                                From {price.effective_from}:{" "}
                                {price.unpriced
                                  ? "Unpriced"
                                  : `${price.input_price} input / ${price.output_price ?? "n/a"} output / ${price.cached_input_price ?? "n/a"} cached`}{" "}
                                · checked {price.checked_on}
                              </li>
                            ))}
                          </ul>
                        </details>
                      </>
                    ) : (
                      "No effective price"
                    )}
                  </td>
                  <td>
                    {permissionOrg !== scope.org
                      ? "Loading effective team policies…"
                      : permissions[model.name]?.join(", ") ||
                        "No teams allowed in this organisation"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <PageCount
          shown={Math.min(shown, rows.length)}
          total={rows.length}
          more={shown < rows.length}
          onMore={() => set({ shown: String(shown + 25) })}
        />
      </section>
      <section className="panel">
        <h2>Aliases</h2>
        <table>
          <thead>
            <tr>
              <SortHeading field="name">Alias</SortHeading>
              <th>Targets and weights</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(catalog.data?.aliases ?? {})
              .sort(([a], [b]) =>
                params.get("direction") === "desc" ? b.localeCompare(a) : a.localeCompare(b),
              )
              .map(([name, targets]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>
                    {targets.map((target) => (
                      <div key={target.model}>
                        {target.model} · weight {target.weight}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        <PageCount
          shown={Object.keys(catalog.data?.aliases ?? {}).length}
          total={Object.keys(catalog.data?.aliases ?? {}).length}
        />
      </section>
    </>
  );
}
