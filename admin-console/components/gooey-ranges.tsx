"use client";
import { GooeyRangeNeck } from "./gooey-range-neck";
import { startTransition, useOptimistic, useRef } from "react";
import { useGooeyRangeMotion } from "./use-gooey-range-motion";

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
  const selected = items.findIndex((item) => Math.abs(item.duration - duration) < 1000);
  const [active, showSelection] = useOptimistic(selected);
  const list = useRef<HTMLUListElement>(null);
  const immediateRef = useRef(false);
  useGooeyRangeMotion(list, active, immediateRef);
  let shift = 0;
  return (
    <div className="gooey-ranges" role="group" aria-label="Quick ranges">
      <ul className="gooey-ranges-list" ref={list}>
        {items.map((item, index) => {
          const leftOpen = index === 0 || index === active || index - 1 === active;
          const rightOpen = index === items.length - 1 || index === active || index + 1 === active;
          if (index > 0 && leftOpen) shift++;
          return (
            <li
              className="gooey-range-segment"
              data-left-open={leftOpen}
              data-right-open={rightOpen}
              data-active={index === active}
              data-shift={shift}
              key={item.label}
            >
              {index > 0 && (
                <GooeyRangeNeck active={index === active} leftActive={index - 1 === active} />
              )}
              <button
                type="button"
                className="gooey-range-button"
                aria-pressed={index === active}
                onClick={(event) => {
                  immediateRef.current = event.detail === 0;
                  startTransition(() => {
                    showSelection(index);
                    onSelect(item.value);
                  });
                }}
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
