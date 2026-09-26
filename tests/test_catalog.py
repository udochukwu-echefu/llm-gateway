from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from llm_gateway.catalog import Catalog, load_catalog
from llm_gateway.config import Settings
from llm_gateway.main import create_app
from tests.conftest import MemoryKeyRepository


def test_reviewed_catalog_loads() -> None:
    catalog = load_catalog()

    assert catalog.version
    assert {entry.provider for entry in catalog.models} == {"groq", "deepseek", "gemini", "openai"}
    assert all(isinstance(entry.input_price, Decimal) for entry in catalog.models)


def test_catalog_version_is_required() -> None:
    with pytest.raises(ValidationError, match="version"):
        Catalog.model_validate({"models": []})


def test_invalid_catalog_prevents_gateway_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    memory_repository: MemoryKeyRepository,
) -> None:
    directory = tmp_path / "catalog"
    directory.mkdir()
    (directory / "models.toml").write_text('version = "v1"\n[[models]]\nprovider = "unknown"\n')
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError):
        create_app(settings, key_repository=memory_repository)


@pytest.mark.parametrize(
    "mutation",
    [
        {"version": None},
        {"version": ""},
        {"input_price": "-0.01"},
        {"input_price": 0.1},
        {"output_price": "-1"},
        {"cached_input_price": "1"},
        {"provider": "unknown"},
        {"extra": "not allowed"},
        {"checked_on": "not-a-date"},
        {"currency": "EUR"},
    ],
)
def test_invalid_catalog_entries_are_rejected(mutation: dict[str, object]) -> None:
    entry = load_catalog().models[0].model_dump(mode="python")
    data = {"version": mutation.get("version", "v1"), "models": [entry]}
    entry.update({key: value for key, value in mutation.items() if key != "version"})

    with pytest.raises(ValidationError):
        Catalog.model_validate(data)


def test_duplicate_provider_model_is_rejected_even_across_kinds() -> None:
    entry = load_catalog().models[0]
    other_kind = entry.model_copy(update={"kind": "embedding", "output_price": None})

    with pytest.raises(ValidationError, match="duplicate"):
        Catalog.model_validate({"version": "v1", "models": [entry, other_kind]})


def test_embedding_cannot_have_an_output_price() -> None:
    entry = load_catalog().models[-1].model_dump()
    entry["output_price"] = Decimal("0.1")

    with pytest.raises(ValidationError):
        Catalog.model_validate({"version": "v1", "models": [entry]})
