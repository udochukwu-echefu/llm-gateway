"use client";
// DevClub's organic Bézier neck, drawn with SVG attributes instead of inline styles.
// License: public/licenses/devclub-components.txt.
import { useId } from "react";

export function GooeyRangeNeck({ active, leftActive }: { active: boolean; leftActive: boolean }) {
  const id = `gooey-neck-${useId().replace(/:/g, "")}`;
  return (
    <svg
      width="16"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      className="gooey-range-neck"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={id} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" className="gooey-neck-stop" data-active={leftActive} />
          <stop offset="100%" className="gooey-neck-stop" data-active={active} />
        </linearGradient>
      </defs>
      <path fill={`url(#${id})`} />
    </svg>
  );
}

export function drawGooeyNeck(path: SVGPathElement, gap: number, span: number) {
  const progress = Math.max(0, gap / (span * 0.85));
  if (!Number.isFinite(progress) || gap <= 0 || progress >= 1) {
    path.setAttribute("d", "");
    return;
  }
  const start = 100 - (gap / span) * 100;
  const middle = (start + 100) / 2;
  const control = (100 - start) * 0.22;
  const halfWaist = 50 * Math.pow(1 - progress, 1.6);
  const top = 50 - halfWaist;
  const bottom = 50 + halfWaist;
  // Cubics reach the true waist; quadratics left a thick bridge that snapped off.
  path.setAttribute(
    "d",
    `M${start} 0 C${start + control} 0 ${middle - control} ${top} ${middle} ${top} C${middle + control} ${top} ${100 - control} 0 100 0 L100 100 C${100 - control} 100 ${middle + control} ${bottom} ${middle} ${bottom} C${middle - control} ${bottom} ${start + control} 100 ${start} 100 Z`,
  );
  const fade = Math.max(0, (progress - 0.6) / 0.4);
  path.setAttribute("fill-opacity", String(1 - fade * fade * (3 - 2 * fade)));
}
