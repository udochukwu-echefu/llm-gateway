from fastapi import APIRouter, Request

from llm_gateway.errors import GatewayError

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Liveness only: the process is up. It deliberately does not call the provider."""
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz(request: Request) -> dict[str, str]:
    try:
        await request.app.state.key_repository.ping()
    except Exception as exc:
        raise GatewayError(
            503, "Database unavailable.", type="server_error", code="database_unavailable"
        ) from exc
    return {"status": "ok"}
