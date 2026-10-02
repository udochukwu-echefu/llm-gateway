// DevClub Sparkle Button optics, adapted to local CSS without a loading toggle.
// License: public/licenses/devclub-components.txt.
import type { ComponentProps } from "react";
export function SparkleButton({
  text,
  ...props
}: Omit<ComponentProps<"button">, "children" | "className" | "aria-label"> & { text: string }) {
  return (
    <button type="button" {...props} className="sparkle-button" aria-label={text}>
      <span className="sparkle-button-content" aria-hidden="true">
        <span className="sparkle-button-label">
          {Array.from(text).map((letter, index) => (
            <span className="sparkle-button-letter" key={index}>
              {letter === " " ? "\u00a0" : letter}
            </span>
          ))}
        </span>
      </span>
    </button>
  );
}
