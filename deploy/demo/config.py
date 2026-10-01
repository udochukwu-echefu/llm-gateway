"""Stdlib-only appliance configuration; fixed loopback boundaries and safe errors."""

import base64
import binascii
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

FAKE_URL = "http://127.0.0.1:18000/v1"
PROVIDERS = ("groq", "deepseek", "gemini", "openai", "zai", "nvidia")
INTERNAL_HOST = "127.0.0.1"
CONSOLE_PORT = 3000


def appliance_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if source is None else source)
    try:
        port = int(env.get("PORT", str(CONSOLE_PORT)))
        if port != CONSOLE_PORT:
            raise ValueError("PORT must match image EXPOSE 3000; deploy with --port 3000.")
        _validate_secrets(env)
        database = normalize_database_url(env.get("DATABASE_URL", ""))
        redis = urlsplit(env.get("REDIS_URL", ""))
        if redis.scheme not in {"redis", "rediss"} or not redis.hostname:
            raise ValueError("Bind a valid REDIS_URL to the appliance.")
        _validate_origin(env.get("ADMIN_CONSOLE_ORIGIN", ""))
        _reject_unsafe_overrides(env)
        try:
            window_s = int(env.get("DEMO_TRAFFIC_WINDOW_S", "600"))
            if window_s <= 0:
                raise ValueError
        except ValueError:
            raise ValueError("Demo traffic window must be a positive integer.") from None
    except ValueError as exc:
        # Only fixed messages above may cross this boundary, never URL parsing errors.
        if str(exc).startswith(("PORT ", "GATEWAY_", "ADMIN_", "Bind ", "Demo ")):
            raise
        raise ValueError(
            "Invalid appliance configuration; check bound services and PORT."
        ) from None
    # No inherited developer settings, secrets backend, tracing endpoint or alternate listener.
    env = {
        name: value
        for name, value in env.items()
        if not name.startswith("GATEWAY_")
        or name in {"GATEWAY_API_KEY_PEPPER", "GATEWAY_CACHE_ENCRYPTION_KEY"}
    }
    env.update(_fixed_environment(database, env["REDIS_URL"], port))
    env["DEMO_TRAFFIC_WINDOW_S"] = str(window_s)
    return env


def normalize_database_url(value: str) -> str:
    try:
        url = urlsplit(value)
        if url.scheme not in {"postgres", "postgresql", "postgresql+asyncpg"} or not (
            url.hostname and url.username and url.password and url.path.strip("/")
        ):
            raise ValueError
        # asyncpg uses `ssl`, while libpq credential bindings commonly use `sslmode`.
        query = [("ssl" if key == "sslmode" else key, item) for key, item in parse_qsl(url.query)]
        return urlunsplit(("postgresql+asyncpg", url.netloc, url.path, urlencode(query), ""))
    except ValueError:
        raise ValueError("Bind a credential-bearing DATABASE_URL to the appliance.") from None


def _validate_secrets(env: dict[str, str]) -> None:
    for name in ("GATEWAY_API_KEY_PEPPER", "ADMIN_CONSOLE_SESSION_SECRET"):
        if len(env.get(name, "").encode()) < 32:
            raise ValueError(f"{name} must have at least 32 bytes.")
    try:
        decoded = base64.b64decode(env.get("GATEWAY_CACHE_ENCRYPTION_KEY", ""), validate=True)
        if len(decoded) != 32:
            raise ValueError
    except (ValueError, binascii.Error):
        raise ValueError("GATEWAY_CACHE_ENCRYPTION_KEY must encode 32 random bytes.") from None


def _validate_origin(value: str) -> None:
    origin = urlsplit(value)
    if (
        origin.scheme not in {"http", "https"}
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.query
        or origin.fragment
        or origin.path not in {"", "/"}
    ):
        raise ValueError("ADMIN_CONSOLE_ORIGIN must be a plain HTTP(S) origin.")


def _reject_unsafe_overrides(env: dict[str, str]) -> None:
    for name, value in env.items():
        if name == "GATEWAY_PROVIDERS":
            raise ValueError("Demo appliance refuses inherited provider JSON configuration.")
        if name.startswith("GATEWAY_PROVIDERS__"):
            expected = FAKE_URL if name.endswith("__BASE_URL") else "synthetic-placeholder"
            if value != expected:
                raise ValueError("Demo appliance refuses external provider configuration.")
        if name in {"GATEWAY_ADMIN_API__HOST", "GATEWAY_METRICS__HOST"} and value != INTERNAL_HOST:
            raise ValueError("Demo internal listeners must bind 127.0.0.1.")


def _fixed_environment(database: str, redis: str, port: int) -> dict[str, str]:
    return {
        "PORT": str(port),
        "HOSTNAME": "0.0.0.0",  # noqa: S104 -- console is the sole public listener
        "DEMO_MODE": "true",
        "DEMO_ALLOW_KEY_SIGN_IN": "false",
        "GATEWAY_DATABASE_URL": database,
        "GATEWAY_REDIS_URL": redis,
        "GATEWAY_DEMO_DEPLOYMENT": "true",
        "GATEWAY_DEMO_SEED": "1",
        "GATEWAY_DEMO_SEED_SIGNIN_KEYS": "0",
        "GATEWAY_DEMO_SEED_TOP_UP": "1",
        "GATEWAY_DEMO_SEED_ALLOW_REMOTE": "1",
        "GATEWAY_ADMIN_API__ENABLED": "true",
        "GATEWAY_ADMIN_API__HOST": INTERNAL_HOST,
        "GATEWAY_ADMIN_API__PORT": "18091",
        "GATEWAY_METRICS__ENABLED": "true",
        "GATEWAY_METRICS__HOST": INTERNAL_HOST,
        "GATEWAY_METRICS__PORT": "19464",
        "GATEWAY_LOG_LEVEL": "WARNING",
        "GATEWAY_TRACING": '{"otlp_endpoint":null}',
        "GATEWAY_SECRETS__BACKEND": "env",
        "GATEWAY_LIMITS__FAIL_MODE": "closed",
        "GATEWAY_LIMITS__BUDGET_RECONCILE_INTERVAL_S": "3600",
        # A single receipt flushes immediately; empty queues wait without short wakeups.
        "GATEWAY_USAGE_BATCH_SIZE": "1",
        "GATEWAY_USAGE_FLUSH_INTERVAL_S": "3600",
        "NEXT_TELEMETRY_DISABLED": "1",
        "ADMIN_API_URL": "http://127.0.0.1:18091",
        "PYTHONPATH": "/app",
        **{f"GATEWAY_PROVIDERS__{name.upper()}__BASE_URL": FAKE_URL for name in PROVIDERS},
        **{
            f"GATEWAY_PROVIDERS__{name.upper()}__API_KEY": "synthetic-placeholder"
            for name in PROVIDERS
        },
    }
