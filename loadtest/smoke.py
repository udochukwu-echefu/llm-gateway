"""One 30-second CI smoke; no secrets, real providers or noisy tail-latency target."""

from loadtest.run import run_once
from loadtest.runtime import compose
from loadtest.setup import setup


def main() -> None:
    setup()
    validate_streams()
    run = run_once("smoke", 5, 30, 1, 1)
    p99 = run["overhead_ms"]["p99"]
    if (
        p99 is None
        or p99 >= 50
        or run["error_rate"]
        or run["dropped_iterations"]
        or not run["measurement_complete"]
    ):
        raise SystemExit("Smoke failed: missing/excessive overhead, errors or dropped iterations")


def validate_streams() -> None:
    """Run structural stream checks without HTTP before trusting CI measurements."""
    compose(
        "run", "--rm", "--no-deps", "k6", "run", "--quiet", "/scripts/stream-validation.test.js"
    )


if __name__ == "__main__":
    main()
