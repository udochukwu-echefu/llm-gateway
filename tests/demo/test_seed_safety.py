"""Managed seeding is allowed only by the complete demo-only opt-in, before any I/O."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llm_gateway.demo.safety import DemoSeedError
from scripts.seed_demo import seed_demo
from tests.conftest import TEST_PEPPER


@pytest.mark.parametrize("deployment", [False, True])
@pytest.mark.parametrize("allow_remote", [False, True])
@pytest.mark.parametrize("skip_signin_files", [False, True])
async def test_managed_seed_requires_every_demo_safety_flag_before_io(
    monkeypatch: pytest.MonkeyPatch,
    deployment: bool,
    allow_remote: bool,
    skip_signin_files: bool,
) -> None:
    monkeypatch.setenv("GATEWAY_DEMO_SEED", "1")
    monkeypatch.setenv("GATEWAY_DEMO_DEPLOYMENT", "true" if deployment else "false")
    monkeypatch.setenv("GATEWAY_DEMO_SEED_ALLOW_REMOTE", "1" if allow_remote else "0")
    monkeypatch.setenv("GATEWAY_DEMO_SEED_SIGNIN_KEYS", "0" if skip_signin_files else "1")
    engine = create_async_engine("postgresql+asyncpg://fake:fake@managed.fake.invalid/demo")

    async def stop_before_io(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Seed authorized; intercepted before database I/O.")

    monkeypatch.setattr(AsyncSession, "execute", stop_before_io)
    authorized = deployment and allow_remote and skip_signin_files

    try:
        with pytest.raises(
            RuntimeError if authorized else DemoSeedError,
            match="Seed authorized" if authorized else "database host must be local",
        ):
            await seed_demo(async_sessionmaker(engine), TEST_PEPPER.encode())
    finally:
        await engine.dispose()
