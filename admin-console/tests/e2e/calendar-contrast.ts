import type { Page } from "@playwright/test";
import { expect } from "./fixtures";
import { settleCalendar } from "./calendar-controls";

export async function weekdayContrast(page: Page) {
  await settleCalendar(page);
  const labels = page.locator(".calendar-weekdays").first();
  const box = await labels.boundingBox();
  expect(box).not.toBeNull();
  const background = await page.screenshot({
    clip: { x: Math.ceil(box!.x), y: Math.ceil(box!.y), width: 2, height: 2 },
  });
  const foreground = await labels.evaluate((element) => getComputedStyle(element).color);
  return page.evaluate(
    async ({ png, foreground }) => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 2;
      const context = canvas.getContext("2d")!;
      const image = new Image();
      image.src = `data:image/png;base64,${png}`;
      await image.decode();
      context.drawImage(image, 0, 0);
      const surface = Array.from(context.getImageData(0, 0, 1, 1).data).slice(0, 3);
      context.fillStyle = foreground;
      context.fillRect(0, 0, 2, 2);
      const text = Array.from(context.getImageData(0, 0, 1, 1).data).slice(0, 3);
      function luminance(rgb: number[]) {
        const linear = rgb.map((channel) => {
          const value = channel / 255;
          return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
        });
        return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
      }
      const values = [luminance(text), luminance(surface)].sort((a, b) => a - b);
      return { foreground, text, surface, ratio: (values[1] + 0.05) / (values[0] + 0.05) };
    },
    { png: background.toString("base64"), foreground },
  );
}
