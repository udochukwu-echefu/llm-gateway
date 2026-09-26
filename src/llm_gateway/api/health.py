from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Liveness only: the process is up. It deliberately does not call the provider."""
    return {"status": "ok"}
