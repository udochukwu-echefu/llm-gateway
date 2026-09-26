import pytest
from fastapi import FastAPI

from llm_gateway.gateway_state import GatewayState, get_app_state
from tests.conftest import MemoryKeyRepository


def test_typed_state_is_unavailable_before_lifespan(app: FastAPI) -> None:
    with pytest.raises(RuntimeError, match="lifespan has not started"):
        get_app_state(app)


async def test_lifespan_installs_typed_resources_once(
    app: FastAPI, memory_repository: MemoryKeyRepository
) -> None:
    async with app.router.lifespan_context(app):
        state: GatewayState = get_app_state(app)

        assert state is get_app_state(app)
        assert state.key_repository is memory_repository
