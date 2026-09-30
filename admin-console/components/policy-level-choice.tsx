"use client";
export type ListMode = "inherit" | "only" | "nothing";
export function PolicyLevelChoice({
  title,
  mode,
  onChange,
  regions = false,
}: {
  title: string;
  mode: ListMode;
  onChange: (mode: ListMode) => void;
  regions?: boolean;
}) {
  return (
    <fieldset className="policy-mode">
      <legend>{title}</legend>
      {(
        [
          ["inherit", "No restriction (inherit)"],
          ["only", regions ? "Allow only these regions" : "Allow only these"],
          ["nothing", regions ? "Allow no regions" : "Allow nothing"],
        ] as const
      ).map(([value, label]) => (
        <label className="check" key={value}>
          <input
            type="radio"
            name={title}
            checked={mode === value}
            onChange={() => onChange(value)}
          />
          {label}
        </label>
      ))}
    </fieldset>
  );
}
