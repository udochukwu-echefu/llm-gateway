"""One 30-second CI smoke; no secrets, real providers or noisy tail-latency target."""

from loadtest.run import run_once
from loadtest.setup import setup


def main() -> None:
    setup()
    run = run_once("smoke", 5, 30, 1, 1)
    p99 = run["overhead_ms"]["p99"]
    if p99 is None or p99 >= 50 or run["error_rate"] or run["dropped_iterations"]:
        raise SystemExit("Smoke failed: missing/excessive overhead, errors or dropped iterations")


if __name__ == "__main__":
    main()
