"use client";
import { GooeyRangeNeck } from "./gooey-range-neck";

export function GooeyRanges({
  items,
  since,
  until,
  onSelect,
}: {
  items: { label: string; value: number; duration: number }[];
  since: string | null;
  until: string | null;
  onSelect: (value: number) => void;
}) {
  const duration = since && until ? Date.parse(until) - Date.parse(since) : Number.NaN;
  const active = items.findIndex((item) => Math.abs(item.duration - duration) < 1000);
  return (
    <div className="gooey-ranges" role="group" aria-label="Quick ranges">
      <ul className="gooey-ranges-list">
        {items.map((item, index) => {
          const leftOpen = index === 0 || index === active || index - 1 === active;
          const rightOpen = index === items.length - 1 || index === active || index + 1 === active;
          return (
            <li
              className="gooey-range-segment"
              data-left-open={leftOpen}
              data-right-open={rightOpen}
              data-active={index === active}
              key={item.label}
            >
              {index > 0 && (
                <GooeyRangeNeck
                  active={index === active}
                  leftActive={index - 1 === active}
                  selection={active}
                />
              )}
              <button
                type="button"
                className="gooey-range-button"
                aria-pressed={index === active}
                onClick={() => onSelect(item.value)}
              >
                {item.label}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
