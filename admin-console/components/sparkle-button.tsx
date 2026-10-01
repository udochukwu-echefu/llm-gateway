// DevClub Sparkle Button optics, adapted to local CSS without a loading toggle.
// License: public/licenses/devclub-components.txt.
export function SparkleButton({ text }: { text: string }) {
  return (
    <button type="submit" className="sparkle-button" aria-label={text}>
      <span className="sparkle-button-content" aria-hidden="true">
        <span className="sparkle-button-icon" />
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
