"""Disposable real gateway stack. Never loads .env or contacts a provider."""

import asyncio
import os
import signal
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[3]
STATE = Path(__file__).with_name(".state.json")
BASE_URL = os.environ.get(
    "CONSOLE_TEST_DATABASE_URL",
    "postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway",
)
DATABASE = "console_e2e_" + uuid.uuid4().hex
URL = BASE_URL.rsplit("/", 1)[0] + "/" + DATABASE
ENV = {
    "PATH": os.environ.get("PATH", ""),
    "GATEWAY_DATABASE_URL": URL,
    "GATEWAY_REDIS_URL": os.environ.get("CONSOLE_TEST_REDIS_URL", "redis://127.0.0.1:6379/15"),
    "GATEWAY_PROVIDERS__GROQ__API_KEY": "obviously-fake-no-provider-calls",
    "GATEWAY_PROVIDERS__GROQ__BASE_URL": "http://127.0.0.1:1/v1",
    "GATEWAY_API_KEY_PEPPER": "obviously-fake-e2e-pepper-at-least-32-bytes",
    "GATEWAY_CACHE__ENABLED": "false",
    "GATEWAY_DEMO_SEED": "1",
    "GATEWAY_DEMO_KEYS_FILE": str(STATE.with_name(".demo-keys.e2e.env")),
    "GATEWAY_METRICS__ENABLED": "false",
    "GATEWAY_ADMIN_API__ENABLED": "true",
    "GATEWAY_ADMIN_API__HOST": "127.0.0.1",
    "GATEWAY_ADMIN_API__PORT": "18091",
    "GATEWAY_LOG_LEVEL": "WARNING",
}


async def database(create: bool) -> None:
    engine = create_async_engine(BASE_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        if create:
            await connection.execute(text(f'CREATE DATABASE "{DATABASE}"'))
        else:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{DATABASE}" WITH (FORCE)'))
    await engine.dispose()


def main() -> None:
    asyncio.run(database(True))
    try:
        subprocess.run(  # noqa: S603 -- fixed repo executable/arguments; no shell or user command.
            [str(ROOT / ".venv/bin/alembic"), "upgrade", "head"], cwd=ROOT, env=ENV, check=True
        )
        subprocess.run(  # noqa: S603 -- fixed synthetic seeder; explicit fake environment.
            [sys.executable, str(ROOT / "scripts/seed_demo.py")], cwd=ROOT, env=ENV, check=True
        )
        subprocess.run(  # noqa: S603 -- fixed repo executable/arguments; no shell or user command.
            [sys.executable, str(Path(__file__).with_name("seed.py"))],
            cwd=ROOT,
            env={**ENV, "CONSOLE_STATE_FILE": str(STATE)},
            check=True,
        )
        process = subprocess.Popen(  # noqa: S603 -- fixed repo executable/arguments; no shell.
            [
                str(ROOT / ".venv/bin/uvicorn"),
                "llm_gateway.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "18090",
                "--no-access-log",
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env=ENV,
        )

        def stop(signum: int, frame: object) -> None:
            process.terminate()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        process.wait()
    finally:
        STATE.unlink(missing_ok=True)
        STATE.with_name(".demo-keys.e2e.env").unlink(missing_ok=True)
        asyncio.run(database(False))


if __name__ == "__main__":
    main()
