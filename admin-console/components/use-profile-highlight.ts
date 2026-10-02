"use client";
import { useCallback, useEffect, useRef } from "react";

export function useProfileHighlight(open: boolean) {
  const highlight = useRef<HTMLDivElement>(null);
  const animation = useRef<Animation | null>(null);
  useEffect(() => () => animation.current?.cancel(), []);
  useEffect(() => {
    if (!open) animation.current?.cancel();
  }, [open]);
  const moveTo = useCallback((element: HTMLElement) => {
    const node = highlight.current;
    if (!node?.animate) return;
    const current = getComputedStyle(node);
    const from = {
      transform: current.transform,
      width: current.width,
      height: current.height,
      opacity: current.opacity,
    };
    animation.current?.cancel();
    animation.current = node.animate(
      [
        from,
        {
          transform: `translate(${element.offsetLeft}px, ${element.offsetTop}px)`,
          width: `${element.offsetWidth}px`,
          height: `${element.offsetHeight}px`,
          opacity: 1,
        },
      ],
      {
        duration: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? 0 : 250,
        easing: "cubic-bezier(0.16, 1, 0.3, 1)",
        fill: "forwards",
      },
    );
  }, []);
  return { highlight, moveTo };
}
