import type { EffectiveModels } from "@/lib/policy-contracts";
export function OverrideList({ title, values }: { title: string; values: string[] | null }) {
  return (
    <div>
      <h3>{title}</h3>
      {values === null ? (
        <p>No restriction (inherit)</p>
      ) : values.length ? (
        <ul>
          {values.map((v) => (
            <li key={v}>
              <code>{v}</code>
            </li>
          ))}
        </ul>
      ) : (
        <p>Allow nothing</p>
      )}
    </div>
  );
}
export function EffectiveModelsView({ effective }: { effective: EffectiveModels }) {
  return (
    <div className="effective-models">
      <h3>Effective models · {effective.models.length}</h3>
      {effective.models.length ? (
        <ul>
          {effective.models.map((name) => (
            <li key={name}>
              <code>{name}</code>
            </li>
          ))}
        </ul>
      ) : (
        <p>No usable models.</p>
      )}
      <h3>Effective aliases · {effective.aliases.length}</h3>
      <p>{effective.aliases.join(", ") || "No usable aliases."}</p>
      <p className="muted">
        From the API. Runtime use also requires a configured provider and active prices.
      </p>
    </div>
  );
}
