from datetime import UTC, datetime, timedelta, timezone
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
    assert all(
        isinstance(period.input_price, Decimal)
        for entry in catalog.models
        for period in entry.periods
    )


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
    for key, value in mutation.items():
        if key == "version":
            continue
        target = (
            entry["periods"][0]
            if key
            in {"input_price", "cached_input_price", "output_price", "checked_on", "currency"}
            else entry
        )
        target[key] = value

    with pytest.raises(ValidationError):
        Catalog.model_validate(data)


def test_duplicate_provider_model_is_rejected_even_across_kinds() -> None:
    entry = load_catalog().models[0]
    other_kind = entry.model_copy(
        update={
            "kind": "embedding",
            "periods": [entry.periods[0].model_copy(update={"output_price": None})],
        }
    )

    with pytest.raises(ValidationError, match="duplicate"):
        Catalog.model_validate({"version": "v1", "models": [entry, other_kind]})


def test_embedding_cannot_have_an_output_price() -> None:
    entry = load_catalog().models[-1].model_dump()
    entry["periods"][0]["output_price"] = Decimal("0.1")

    with pytest.raises(ValidationError):
        Catalog.model_validate({"version": "v1", "models": [entry]})


@pytest.mark.parametrize("dates", [[], ["2026-09-26", "2026-09-26"], ["2027-01-01", "2026-09-26"]])
def test_price_periods_must_be_nonempty_unique_and_increasing(dates: list[str]) -> None:
    entry = load_catalog().models[0].model_dump(mode="python")
    template = entry["periods"][0]
    entry["periods"] = [
        {**template, "effective_from": datetime.fromisoformat(day).date()} for day in dates
    ]

    with pytest.raises(ValidationError):
        Catalog.model_validate({"version": "v1", "models": [entry]})


def test_each_period_applies_validation_rules() -> None:
    entry = load_catalog().models[3].model_dump(mode="python")
    entry["periods"][1]["cached_input_price"] = Decimal("2")

    with pytest.raises(ValidationError, match="cached price"):
        Catalog.model_validate({"version": "v1", "models": [entry]})


def test_gemini_price_changes_at_midnight_utc() -> None:
    price = load_catalog().find("gemini", "gemini-3.8-flash", "chat")
    assert price is not None
    before = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    after = datetime(2027, 1, 1, tzinfo=UTC)

    old_period = price.at(before)
    new_period = price.at(after)
    assert old_period is not None
    assert new_period is not None
    assert old_period.input_price == Decimal("0.75")
    assert new_period.input_price == Decimal("1.50")
    assert price.at(after - timedelta(hours=1)) == price.periods[0]
    assert price.at(after.astimezone(timezone(timedelta(hours=-5)))) == price.periods[1]
