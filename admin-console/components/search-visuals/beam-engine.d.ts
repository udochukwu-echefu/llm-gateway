export function createBeam(
  host: HTMLElement,
  canvas: HTMLCanvasElement,
  halo: HTMLCanvasElement,
): {
  paint(now: number, level: number, processing: boolean, reducedMotion: boolean): void;
  destroy(): void;
};
