"use client";
// DevClub's organic Bézier neck, drawn with SVG attributes instead of inline styles.
// License: public/licenses/devclub-components.txt.
import { useEffect, useId, useRef } from "react";

export function GooeyRangeNeck({
  active,
  leftActive,
  selection,
}: {
  active: boolean;
  leftActive: boolean;
  selection: number;
}) {
  const id = `gooey-neck-${useId().replace(/:/g, "")}`;
  const svg = useRef<SVGSVGElement>(null);
  const path = useRef<SVGPathElement>(null);
  useEffect(() => {
    const segment = svg.current?.parentElement;
    const previous = segment?.previousElementSibling;
    if (!segment || !previous || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      path.current?.setAttribute("d", "");
      return;
    }
    let frame = 0;
    const started = performance.now();
    function draw(now: number) {
      const gap = segment!.getBoundingClientRect().left - previous!.getBoundingClientRect().right;
      path.current?.setAttribute("d", neckPath(gap));
      if (now - started < 400) frame = requestAnimationFrame(draw);
    }
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [selection]);
  return (
    <svg
      ref={svg}
      width="16"
      viewBox="0 0 16 100"
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
      <path ref={path} fill={`url(#${id})`} />
    </svg>
  );
}

function neckPath(gap: number): string {
  const span = 16;
  if (!Number.isFinite(gap) || gap <= 0) return "";
  const progress = gap / (span * 0.44);
  if (progress >= 1) return "";
  const waist = 100 * Math.pow(1 - progress, 1.4);
  if (waist <= 0.2) return "";
  const start = span - gap;
  const mid = start + gap / 2;
  const dip = (100 - waist) / 2;
  return `M${start} 0 Q${mid} ${dip} ${span} 0 L${span} 100 Q${mid} ${100 - dip} ${start} 100 Z`;
}
