"""A read-only catalogue DTO deliberately omits prices, credentials and URLs."""

from datetime import UTC, datetime

from fastapi import APIRouter

from llm_gateway.catalog import load_catalog
from llm_gateway.guardrails.policy import REGIONS

router = APIRouter()


@router.get("/catalog")
async def get_catalog() -> dict[str, object]:
    catalog = load_catalog()
    now = datetime.now(UTC)
    return {
        "regions": list(REGIONS),
        "models": [
            {
                "name": f"{entry.provider}/{entry.model}",
                "provider": entry.provider,
                "region": entry.region,
                "endpoints": ["chat" if entry.kind == "chat" else "embeddings"],
                "priced": (period := entry.at(now)) is not None and not period.unpriced,
            }
            for entry in catalog.models
        ],
        "aliases": {
            name: [{"model": target.model, "weight": target.weight} for target in alias.targets]
            for name, alias in catalog.aliases.items()
        },
    }
