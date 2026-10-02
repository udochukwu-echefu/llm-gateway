// DevClub RevealSheet default timeline, expressed through Web Animations to avoid inline styles.
// MIT license: public/licenses/devclub-components.txt.
export const sheetDuration = 1180;
function progress(time: number, start: number, duration: number) {
  return Math.max(0, Math.min(1, (time - start) / duration));
}
function easeOut(value: number, power: number) {
  return 1 - (1 - value) ** power;
}
function easeInOut(value: number, power: number) {
  return value < 0.5 ? (2 * value) ** power / 2 : 1 - (2 - 2 * value) ** power / 2;
}
export function revealSheet(panel: HTMLDialogElement) {
  const radius = Math.hypot(panel.offsetWidth, panel.offsetHeight / 2) + 2;
  const frames = Array.from({ length: 119 }, (_, index) => {
    const time = index / 100;
    let scale = 1;
    if (time >= 0.54 && time < 0.72) scale = 1 + 0.032 * easeOut(progress(time, 0.54, 0.18), 4);
    else if (time < 0.88 && time >= 0.72)
      scale = 1.032 - 0.04 * easeInOut(progress(time, 0.72, 0.16), 3);
    else if (time < 1.02 && time >= 0.88)
      scale = 0.992 + 0.014 * easeOut(progress(time, 0.88, 0.14), 3);
    else if (time >= 1.02) scale = 1.006 - 0.006 * easeOut(progress(time, 1.02, 0.16), 3);
    return {
      offset: time / 1.18,
      clipPath: `circle(${radius * easeInOut(progress(time, 0, 0.72), 4)}px at 100% 50%)`,
      transform: `scaleX(${scale})`,
    };
  });
  return panel.animate(frames, { duration: sheetDuration, fill: "both" });
}
