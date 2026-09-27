from typing import Any

import pytest
from pydantic import ValidationError

from llm_gateway.catalog import Catalog


@pytest.mark.parametrize("failure", ["self", "unknown", "kind", "cycle"])
def test_invalid_fallback_graph_fails_startup(test_catalog: Catalog, failure: str) -> None:
    data = test_catalog.model_dump()
    entries = data["models"]
    chat = next(e for e in entries if e["kind"] == "chat")
    other = next(e for e in entries if e["kind"] == "chat" and e is not chat)
    embedding = next(e for e in entries if e["kind"] == "embedding")

    def name(e: dict[str, Any]) -> str:
        return f"{e['provider']}/{e['model']}"

    target = {
        "self": name(chat),
        "unknown": "groq/missing",
        "kind": name(embedding),
        "cycle": name(other),
    }[failure]
    chat["fallbacks"] = [target]
    if failure == "cycle":
        other["fallbacks"] = [name(chat)]
    with pytest.raises(ValidationError):
        Catalog.model_validate(data)
