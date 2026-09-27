"""Stable request fingerprints without putting customer text in Redis keys."""

import hashlib
import json
import uuid
from typing import Any, cast

from llm_gateway.schemas.common import ProxiedRequest

EXCLUDED = {"stream_options", "user", "safety_identifier", "provider_options"}


def cache_key(
    team: uuid.UUID, endpoint: str, model: str, request: ProxiedRequest, version: str
) -> str:
    provider = model.split("/", 1)[0]
    fields = request.model_dump(mode="json", exclude=EXCLUDED)
    fields["model"] = model
    options = next(
        (value for name, value in (request.provider_options or {}).items() if name == provider),
        cast(dict[str, Any], {}),
    )
    payload: dict[str, object] = {
        "endpoint": endpoint,
        "model": model,
        "request": fields,
        "provider_options": options,
        "catalog_version": version,
    }
    canonical = json.dumps(
        _normalize(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"lgw:cache:{team}:{digest}"


def _normalize(value: object) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in cast(dict[str, object], value).items()}
    if isinstance(value, list):
        return [_normalize(item) for item in cast(list[object], value)]
    return value
