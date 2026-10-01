type Mark = { x: number; y: number; z: number; r: number; white: number; a?: number };
type Edge = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  white: number;
  a?: number;
  w: number;
};
type Frame = { dots: Mark[]; lines: Edge[] };
type Options = Record<string, number | undefined>;
export const MODE_FRAMES: Record<string, (size: number, time: number, options: Options) => Frame>;
export function resolvePreset(
  state: string,
  size: number,
): { mode: string; speed: number; opts: Options };
export function paintFrame(context: CanvasRenderingContext2D, frame: Frame, dark: boolean): void;
