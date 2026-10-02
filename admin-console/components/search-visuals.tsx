"use client";
import { useEffect, useRef, type ReactNode, type RefObject } from "react";
import { MODE_FRAMES, paintFrame, resolvePreset } from "./search-visuals/orb-engine";
import { createBeam } from "./search-visuals/beam-engine";

export function SearchVisuals({
  busy,
  energy,
  children,
}: {
  busy: boolean;
  energy: RefObject<number>;
  children: ReactNode;
}) {
  const host = useRef<HTMLDivElement>(null);
  const orb = useRef<HTMLCanvasElement>(null);
  const band = useRef<HTMLCanvasElement>(null);
  const halo = useRef<HTMLCanvasElement>(null);
  const state = useRef({ busy });
  const repaint = useRef<(() => void) | null>(null);
  useEffect(() => {
    state.current.busy = busy;
    repaint.current?.();
  }, [busy]);
  useEffect(() => {
    const wrapper = host.current,
      orbCanvas = orb.current,
      bandCanvas = band.current,
      haloCanvas = halo.current;
    if (!wrapper || !orbCanvas || !bandCanvas || !haloCanvas) return;
    const context = orbCanvas.getContext("2d");
    if (!context || !wrapper.animate) return;
    const beam = createBeam(wrapper, bandCanvas, haloCanvas);
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    orbCanvas.width = orbCanvas.height = Math.round(64 * dpr);
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const presets = {
      breathing: resolvePreset("breathing", 64),
      searching: resolvePreset("searching", 64),
    };
    const started = performance.now();
    let frame = 0;
    function paint(now: number) {
      const busy = state.current.busy;
      const time = media.matches ? 0.6 : (now - started) / 1000;
      energy.current *= 0.91;
      const preset = busy ? presets.searching : presets.breathing;
      context!.setTransform(dpr, 0, 0, dpr, 0, 0);
      context!.clearRect(0, 0, 64, 64);
      paintFrame(context!, MODE_FRAMES[preset.mode](64, time * preset.speed, preset.opts), true);
      beam.paint(now, energy.current, busy, media.matches);
      if (!media.matches && document.visibilityState !== "hidden")
        frame = requestAnimationFrame(paint);
    }
    const restart = () => {
      cancelAnimationFrame(frame);
      paint(performance.now());
    };
    const visibility = () => {
      cancelAnimationFrame(frame);
      if (document.visibilityState !== "hidden") restart();
    };
    repaint.current = restart;
    restart();
    media.addEventListener("change", restart);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      cancelAnimationFrame(frame);
      beam.destroy();
      repaint.current = null;
      media.removeEventListener("change", restart);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [energy]);
  return (
    <div ref={host} className="search-voice" data-active="" data-voice-halfres="">
      {children}
      <div className="search-voice-bloom" aria-hidden="true" />
      <div className="search-voice-warp search-voice-warp-inner" aria-hidden="true" />
      <div className="search-voice-warp search-voice-warp-bloom" aria-hidden="true" />
      <canvas ref={halo} className="search-voice-band-halo" aria-hidden="true" />
      <canvas ref={band} className="search-voice-band" aria-hidden="true" />
      <canvas ref={orb} className="search-orb" aria-hidden="true" />
      <svg className="search-voice-filter" aria-hidden="true" width="0" height="0">
        <filter
          id="vb-distort-search"
          x="-20%"
          y="-20%"
          width="140%"
          height="140%"
          colorInterpolationFilters="sRGB"
        >
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.0276 0.1150"
            numOctaves="2"
            seed="7"
            result="noise"
          />
          <feOffset in="noise" dx="0" dy="0" result="moved" />
          <feColorMatrix
            in="moved"
            type="matrix"
            values="1 0 0 0 0  0 0 0 0 0.5  0 0 0 0 0  0 0 0 0 1"
            result="map"
          />
          <feDisplacementMap
            in="SourceGraphic"
            in2="map"
            scale="0"
            xChannelSelector="R"
            yChannelSelector="G"
          />
        </filter>
      </svg>
    </div>
  );
}
