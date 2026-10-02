"use client";
import { useLayoutEffect, type RefObject } from "react";

export function useProfilePlacement(rootRef: RefObject<HTMLDivElement | null>, open: boolean) {
  useLayoutEffect(() => {
    if (!open) return;
    const slot = rootRef.current;
    const card = slot?.querySelector<HTMLElement>(".profile-card");
    const scroll = slot?.querySelector<HTMLElement>(".profile-scroll");
    if (!slot || !card?.animate || !scroll?.animate) return;
    let positions: Animation[] = [];
    let previousPlacement = "";
    function place() {
      const bounds = slot!.getBoundingClientRect();
      const width = Math.min(360, window.innerWidth - 32);
      const height = Math.min(scroll!.scrollHeight + 62, window.innerHeight - 32);
      const top = Math.max(16, Math.min(bounds.top, window.innerHeight - 16 - height));
      const left = Math.max(16, Math.min(bounds.right - width, window.innerWidth - 16 - width));
      const placement = `${top}:${left}:${window.innerHeight}`;
      if (placement === previousPlacement) return;
      previousPlacement = placement;
      positions.forEach((animation) => animation.cancel());
      // Held native effects set measured bounds without inline styles or a frame loop.
      positions = [
        card!.animate({ top: `${top}px`, left: `${left}px` }, { duration: 0, fill: "both" }),
        scroll!.animate(
          { maxHeight: `${Math.max(0, window.innerHeight - top - 78)}px` },
          { duration: 0, fill: "both" },
        ),
      ];
    }
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      positions.forEach((animation) => animation.cancel());
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [rootRef, open]);
}
