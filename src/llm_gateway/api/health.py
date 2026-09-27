from fastapi import APIRouter, Request

from llm_gateway.errors import GatewayError
from llm_gateway.gateway_state import get_state

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Liveness only: the process is up. It deliberately does not call the provider."""
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz(request: Request) -> dict[str, str]:
    state = get_state(request)
    try:
        await state.key_repository.ping()
    except Exception as exc:
        raise GatewayError(
            503, "Database unavailable.", type="server_error", code="database_unavailable"
        ) from exc
    if state.limits is not None:
        try:
            await state.limits.client.ping()  # pyright: ignore[reportUnknownMemberType]  # redis-py types **kwargs as Unknown
        except Exception as exc:
            if state.settings.limits.fail_mode == "closed":
                raise GatewayError(
                    503, "Limits unavailable.", type="server_error", code="limits_unavailable"
                ) from exc
            return {"status": "ok", "redis": "unavailable"}
        return {"status": "ok", "redis": "ok"}
    return {"status": "ok"}
