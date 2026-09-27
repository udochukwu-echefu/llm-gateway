"""Walk provider-visible text without interpreting image, audio or file payloads."""

import json
from collections.abc import Callable
from typing import Any, cast

# Structural identifiers must retain protocol meaning. Arbitrary option/schema values
# are visited too: hiding text in provider_options must not bypass inspection.
STRUCTURAL = frozenset({"model"})
BINARY = frozenset({"image_url", "input_audio", "file", "embedding"})


def transform_text(value: Any, transform: Callable[[str], str], key: str = "") -> Any:
    if key in BINARY or key in STRUCTURAL:
        return value
    if isinstance(value, str):
        if key == "arguments":
            return _arguments(value, transform)
        return transform(value)
    if isinstance(value, list):
        return [transform_text(item, transform) for item in cast(list[Any], value)]
    if isinstance(value, dict):
        return {
            name: transform_text(item, transform, name)
            for name, item in cast(dict[str, Any], value).items()
        }
    return value


def _arguments(value: str, transform: Callable[[str], str]) -> str:
    # Decode JSON escapes so a unicode-escaped secret cannot bypass the scanner.
    try:
        decoded = json.loads(value)
    except ValueError:
        return transform(value)
    changed = _json_text(decoded, transform)
    return value if changed == decoded else json.dumps(changed, ensure_ascii=False)


def _json_text(value: Any, transform: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, list):
        return [_json_text(item, transform) for item in cast(list[Any], value)]
    if isinstance(value, dict):
        return {
            transform(name): _json_text(item, transform)
            for name, item in cast(dict[str, Any], value).items()
        }
    return value
