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
                "maker": entry.model.split("/")[0]
                if "/" in entry.model
                else {
                    "zai": "Z.ai",
                    "gemini": "Google",
                    "deepseek": "DeepSeek",
                    "openai": "OpenAI",
                }.get(entry.provider, "Unknown"),
                "prices": [item.model_dump(mode="json") for item in entry.periods],
                "effective_price": period.model_dump(mode="json") if period else None,
                "region_source_url": str(entry.region_source_url)
                if entry.region_source_url
                else None,
                "region_checked_on": entry.region_checked_on.isoformat()
                if entry.region_checked_on
                else None,
            }
            for entry in catalog.models
        ],
        "aliases": {
            name: [{"model": target.model, "weight": target.weight} for target in alias.targets]
            for name, alias in catalog.aliases.items()
        },
    }
