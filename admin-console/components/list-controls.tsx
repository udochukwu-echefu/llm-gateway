"use client";
import { Select } from "./select";
import type { ReactNode } from "react";
import { useListQuery } from "./use-list-query";
import { DateRangeFields } from "./date-range-fields";
export interface FilterField {
  name: string;
  label: string;
  type?: string;
  options?: string[];
}
export function FilterBar({ fields, children }: { fields: FilterField[]; children?: ReactNode }) {
  const { params, set } = useListQuery();
  const rangeStart = fields.find(
    (field) => field.name === "since" && ["date", "datetime"].includes(field.type ?? ""),
  );
  const rangeEnd = fields.find(
    (field) => field.name === "until" && field.type === rangeStart?.type,
  );
  function fieldValue(name: string, type?: string) {
    const value = params.get(name) ?? "";
    return type === "datetime" && value && Number.isFinite(Date.parse(value))
      ? new Date(value).toISOString().slice(0, 16)
      : value;
  }
  return (
    <>
      <form
        key={params.toString()}
        className="filter-bar"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          set(
            Object.fromEntries(
              fields.map(({ name, type }) => {
                const value = String(form.get(name) ?? "");
                return [
                  name,
                  type === "datetime" && value ? new Date(value + "Z").toISOString() : value,
                ];
              }),
            ),
          );
        }}
      >
        {fields.map(({ name, label, type, options }) => {
          if (rangeStart && rangeEnd && name === rangeEnd.name) return null;
          if (rangeStart && rangeEnd && name === rangeStart.name)
            return (
              <DateRangeFields
                key={name}
                start={{ name, label, value: fieldValue(name, type) }}
                end={{
                  name: rangeEnd.name,
                  label: rangeEnd.label,
                  value: fieldValue(rangeEnd.name, rangeEnd.type),
                }}
                withTime={type === "datetime"}
              />
            );
          return (
            <label key={name}>
              {label}
              {options ? (
                <Select aria-label={label} name={name} defaultValue={params.get(name) ?? ""}>
                  <option value="">All</option>
                  {options.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </Select>
              ) : (
                <input
                  aria-label={label}
                  name={name}
                  type={type === "datetime" ? "datetime-local" : (type ?? "text")}
                  defaultValue={
                    type === "datetime" &&
                    params.get(name) &&
                    Number.isFinite(Date.parse(params.get(name)!))
                      ? new Date(params.get(name)!).toISOString().slice(0, 16)
                      : (params.get(name) ?? "")
                  }
                />
              )}
            </label>
          );
        })}
        <button>Apply filters</button>
        {children}
      </form>
      <div className="filter-chips">
        {fields
          .filter((field) => params.has(field.name))
          .map((field) => (
            <button
              className="secondary"
              key={field.name}
              onClick={() => set({ [field.name]: null })}
            >
              {field.label}: {params.get(field.name)} ×
            </button>
          ))}
      </div>
    </>
  );
}
export function SortHeading({
  field,
  children,
  className,
}: {
  field: string;
  children: ReactNode;
  className?: string;
}) {
  const { params, set } = useListQuery();
  const active = params.get("sort") === field;
  const direction = params.get("direction") ?? "asc";
  return (
    <th
      className={className}
      aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}
    >
      <button
        className="sort-heading"
        onClick={() =>
          set({ sort: field, direction: active && direction === "asc" ? "desc" : "asc" })
        }
      >
        {children} {active ? (direction === "asc" ? "↑" : "↓") : "↕"}
      </button>
    </th>
  );
}
export function PageCount({
  shown,
  total,
  more,
  onMore,
}: {
  shown: number;
  total: number;
  more?: boolean;
  onMore?: () => void;
}) {
  return (
    <div className="list-count">
      <span>
        Showing {shown} of {total}
      </span>
      {more && (
        <button className="secondary" onClick={onMore}>
          Load more
        </button>
      )}
    </div>
  );
}
