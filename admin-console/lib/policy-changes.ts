import {
  actions,
  detectors,
  type Action,
  type Detector,
  type GuardrailOverrides,
} from "./policy-contracts";
export function listChanges(before: string[] | null, after: string[] | null): string[] {
  if (before === null && after === null) return [];
  if (after === null) return ["Remove override → no restriction at this level"];
  if (before === null)
    return [
      after.length
        ? `Allow only: ${after.join(", ")}`
        : "Allow nothing → block every model at this level",
    ];
  return [
    ...after.filter((v) => !before.includes(v)).map((v) => `Added: ${v}`),
    ...before.filter((v) => !after.includes(v)).map((v) => `Removed: ${v}`),
  ];
}
export function guardrailChanges(before: GuardrailOverrides, after: GuardrailOverrides) {
  return detectors
    .filter((d) => before[d] !== after[d])
    .map((d) => `${d}: ${before[d] ?? "inherit"} → ${after[d] ?? "inherit"}`);
}
export function weakensGuardrails(before: GuardrailOverrides, after: GuardrailOverrides) {
  return detectors.some(
    (d) => before[d] && (!after[d] || actions.indexOf(after[d]) < actions.indexOf(before[d])),
  );
}
export function noEffect(
  detector: Detector,
  choice: Action | undefined,
  defaults: Record<Detector, Action>,
  org?: GuardrailOverrides,
) {
  if (!choice) return "";
  const floor = defaults[detector];
  const inherited = org?.[detector];
  if (
    inherited &&
    actions.indexOf(inherited) > actions.indexOf(choice) &&
    actions.indexOf(inherited) >= actions.indexOf(floor)
  )
    return `No effect: the organisation already requires ${inherited}`;
  return actions.indexOf(floor) > actions.indexOf(choice)
    ? `No effect: the built-in default already requires ${floor}`
    : "";
}
