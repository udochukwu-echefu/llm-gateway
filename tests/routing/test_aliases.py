import pytest
from pydantic import ValidationError

from llm_gateway.catalog import Catalog


@pytest.mark.parametrize(
    "name", ["", "Fast", "a/b", "-fast", "x" * 33, "groq", "deepseek", "gemini", "openai"]
)
def test_alias_name_validation(name: str, test_catalog: Catalog) -> None:
    with pytest.raises(ValidationError, match="alias"):
        Catalog.model_validate(
            {
                **test_catalog.model_dump(),
                "aliases": {name: {"targets": [{"model": "groq/model", "weight": 1}]}},
            }
        )


@pytest.mark.parametrize("weight", [0, -1, True, 1.5, "90"])
def test_alias_weight_is_positive_integer(weight: object, test_catalog: Catalog) -> None:
    with pytest.raises(ValidationError):
        Catalog.model_validate(
            {
                **test_catalog.model_dump(),
                "aliases": {"fast": {"targets": [{"model": "groq/model", "weight": weight}]}},
            }
        )


@pytest.mark.parametrize(
    "targets",
    [
        [],
        ["missing/model"],
        ["fast"],
        ["groq/model", "openai/embedding"],
        ["groq/model", "groq/model"],
    ],
)
def test_alias_targets_are_concrete_unique_and_same_kind(
    targets: list[str], test_catalog: Catalog
) -> None:
    with pytest.raises(ValidationError):
        Catalog.model_validate(
            {
                **test_catalog.model_dump(),
                "aliases": {
                    "fast": {"targets": [{"model": target, "weight": 1} for target in targets]}
                },
            }
        )


def test_valid_aliases_include_nested_model_names(test_catalog: Catalog) -> None:
    catalog = Catalog.model_validate(
        {
            **test_catalog.model_dump(),
            "aliases": {
                "fast-1": {
                    "targets": [
                        {"model": "groq/openai/gpt-oss-20b", "weight": 90},
                        {"model": "deepseek/model", "weight": 10},
                    ]
                }
            },
        }
    )

    assert catalog.aliases["fast-1"].targets[0].weight == 90
