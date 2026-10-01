"""Provisioned values must pass the actual gateway and console startup validators."""

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from deploy.demo.config import appliance_environment
from deploy.demo.set_secrets import set_secrets
from llm_gateway.config import CacheSettings, Settings
from llm_gateway.main import create_app
from tests.conftest import MemoryKeyRepository, OfflineLimitService
from tests.demo.fixtures import demo_environment


def test_generated_secrets_pass_runtime_validators(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, memory_repository: MemoryKeyRepository
) -> None:
    real_run = subprocess.run

    # Force bytes whose standard base64 contains both + and /; the old generator always fails.
    def cache_bytes(size: int) -> bytes:
        return b"\xfb\xff" * (size // 2)

    monkeypatch.setattr("deploy.demo.set_secrets.secrets.token_bytes", cache_bytes)
    monkeypatch.setattr("deploy.demo.set_secrets.shutil.which", Mock(return_value="/fake/insta"))
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr("deploy.demo.set_secrets.subprocess.run", run)

    set_secrets()

    generated = {call.args[0][4]: call.kwargs["input"].decode() for call in run.call_args_list}
    for name in ("GATEWAY_API_KEY_PEPPER", "GATEWAY_CACHE_ENCRYPTION_KEY"):
        monkeypatch.setenv(name, generated[name])
    create_app(
        settings.model_copy(update={"cache": CacheSettings(enabled=True)}),
        key_repository=memory_repository,
        limit_service=OfflineLimitService(),
    )
    appliance_environment({**demo_environment(), **generated})
    # Session configuration belongs to Node; call its shared schema rather than duplicating it.
    script = (
        "import {configSchema} from './admin-console/lib/config-schema.mjs'; "
        "let secret=''; for await (const chunk of process.stdin) secret += chunk; "
        "process.exit(configSchema.safeParse({ADMIN_API_URL:'http://127.0.0.1:1', "
        "ADMIN_CONSOLE_ORIGIN:'https://demo.example.invalid', "
        "ADMIN_CONSOLE_SESSION_SECRET:secret}).success ? 0 : 1);"
    )
    # Keep the real subprocess isolated from the mocked provisioning call.
    result = real_run(
        ["node", "--input-type=module", "-e", script],
        input=generated["ADMIN_CONSOLE_SESSION_SECRET"].encode(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert result.returncode == 0


def test_appliance_rejects_urlsafe_cache_key() -> None:
    env = {**demo_environment(), "GATEWAY_CACHE_ENCRYPTION_KEY": "-" * 43 + "="}

    with pytest.raises(ValueError, match="must encode 32 random bytes"):
        appliance_environment(env)
