"use client";
import { useLayoutEffect, useRef, type RefObject } from "react";
import { drawGooeyNeck } from "./gooey-range-neck";
import { retargetRangeSpring, sampleRangeSpring, type RangeSpring } from "./gooey-range-spring";

interface RangeMotion {
  started: number;
  springs: RangeSpring[];
}
interface RangeKeyframes {
  position: Keyframe[];
  corners: Keyframe[];
}
const duration = 620;
const samples = 38;

export function useGooeyRangeMotion(
  list: RefObject<HTMLUListElement | null>,
  active: number,
  immediateRef: RefObject<boolean>,
) {
  const motion = useRef<RangeMotion | null>(null);
  useLayoutEffect(() => {
    const element = list.current;
    if (!element) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const compact = window.matchMedia("(max-width: 460px)");
    let stop = animateRanges(element, active, reduced.matches || immediateRef.current, motion);
    function changePreference() {
      stop();
      motion.current = null;
      stop = animateRanges(element!, active, reduced.matches, motion);
    }
    reduced.addEventListener("change", changePreference);
    compact.addEventListener("change", changePreference);
    return () => {
      stop();
      reduced.removeEventListener("change", changePreference);
      compact.removeEventListener("change", changePreference);
    };
  }, [list, active, immediateRef]);
}

function animateRanges(
  list: HTMLUListElement,
  active: number,
  reduced: boolean,
  motion: RefObject<RangeMotion | null>,
) {
  const segments = Array.from(list.querySelectorAll<HTMLLIElement>(".gooey-range-segment"));
  const paths = segments.map((segment) =>
    segment.querySelector<SVGPathElement>(".gooey-range-neck path"),
  );
  const span = Number.parseFloat(getComputedStyle(list).getPropertyValue("--gooey-gap")) || 16;
  const timelineTime = document.timeline.currentTime;
  const started = typeof timelineTime === "number" ? timelineTime : performance.now();
  const previous = motion.current;
  const seconds = previous ? Math.max(0, (started - previous.started) / 1000) : 0;
  const springs = segments.map((_, index) => {
    const target = index === 0 ? 0 : index === active || index - 1 === active ? span : -1;
    const old = previous?.springs[index];
    return old && !reduced
      ? retargetRangeSpring(old, seconds, target)
      : { from: target, velocity: 0, target };
  });
  motion.current = { started, springs };
  const isMoving = springs.some(
    ({ from, target, velocity }) => Math.abs(from - target) > 0.001 || Math.abs(velocity) > 0.001,
  );
  if (!isMoving) {
    paths.forEach((path) => path?.setAttribute("d", ""));
    return () => {};
  }
  const frames = rangeKeyframes(springs, span);
  // Separate effects keep transform motion compositable while corners repaint.
  const animations = segments.flatMap((segment, index) =>
    [frames[index].position, frames[index].corners].map((keyframes) => {
      const animation = segment.animate(keyframes, { duration, easing: "linear", fill: "both" });
      animation.startTime = started;
      return animation;
    }),
  );
  return drawConnections(paths, springs, span, started, animations, motion);
}

function rangeKeyframes(springs: RangeSpring[], span: number): RangeKeyframes[] {
  const frames: RangeKeyframes[] = springs.map(() => ({ position: [], corners: [] }));
  for (let sample = 0; sample <= samples; sample++) {
    const offset = sample / samples;
    const gaps = springs.map((spring) =>
      sample === samples
        ? spring.target
        : sampleRangeSpring(spring, (offset * duration) / 1000).position,
    );
    let displacement = 0;
    gaps.forEach((gap, index) => {
      if (index > 0) displacement += gap + 1;
      const left = index === 0 ? 10 : cornerRadius(gap, span);
      const right = index === gaps.length - 1 ? 10 : cornerRadius(gaps[index + 1], span);
      frames[index].position.push({ offset, transform: `translateX(${displacement}px)` });
      frames[index].corners.push({
        offset,
        borderTopLeftRadius: `${left}px`,
        borderBottomLeftRadius: `${left}px`,
        borderTopRightRadius: `${right}px`,
        borderBottomRightRadius: `${right}px`,
      });
    });
  }
  return frames;
}

function cornerRadius(gap: number, span: number): number {
  return 10 * Math.max(0, Math.min(1, (gap + 1) / (span + 1)));
}

function drawConnections(
  paths: (SVGPathElement | null)[],
  springs: RangeSpring[],
  span: number,
  started: number,
  animations: Animation[],
  motion: RefObject<RangeMotion | null>,
) {
  let frame = 0;
  function draw(now: number) {
    const elapsed = Math.max(0, now - started);
    paths.forEach((path, index) => {
      if (path)
        drawGooeyNeck(path, sampleRangeSpring(springs[index], elapsed / 1000).position, span);
    });
    if (elapsed < duration) frame = requestAnimationFrame(draw);
    else {
      motion.current = {
        started: now,
        springs: springs.map(({ target }) => ({ from: target, velocity: 0, target })),
      };
      paths.forEach((path) => path?.setAttribute("d", ""));
      animations.forEach((animation) => animation.cancel());
    }
  }
  frame = requestAnimationFrame(draw);
  return () => {
    cancelAnimationFrame(frame);
    animations.forEach((animation) => animation.cancel());
  };
}
