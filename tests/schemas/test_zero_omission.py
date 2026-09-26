import pytest

from llm_gateway.schemas.chat import Choice, ChunkChoice, ToolCallDelta, Usage
from llm_gateway.schemas.common import ZeroOmittingResponseModel
from llm_gateway.schemas.embeddings import EmbeddingResponse, EmbeddingUsage


@pytest.mark.parametrize(
    ("model", "required", "zero_fields"),
    [
        (Choice, {"message": {}}, {"index"}),
        (ChunkChoice, {"delta": {}}, {"index"}),
        (ToolCallDelta, {}, {"index"}),
        (Usage, {}, {"prompt_tokens", "completion_tokens", "total_tokens"}),
        (EmbeddingUsage, {}, {"prompt_tokens", "total_tokens"}),
    ],
)
def test_omitted_numeric_zeros_are_materialized(
    model: type[ZeroOmittingResponseModel],
    required: dict[str, object],
    zero_fields: set[str],
) -> None:
    result = model.model_validate(required).model_dump(exclude_unset=True)

    assert all(result[field] == 0 for field in zero_fields)


@pytest.mark.parametrize("model", [Choice, ChunkChoice, ToolCallDelta])
def test_explicit_nonzero_indices_are_not_changed(model: type[ZeroOmittingResponseModel]) -> None:
    result = model.model_validate({"index": 3, "message": {}, "delta": {}})

    assert result.model_dump(exclude_unset=True)["index"] == 3


def test_missing_embedding_indices_use_position_and_explicit_indices_are_preserved() -> None:
    response = EmbeddingResponse.model_validate(
        {
            "model": "embedding",
            "data": [
                {"embedding": [0.1], "index": 5},
                {"embedding": [0.2]},
                {"embedding": [0.3], "index": 0},
            ],
        }
    )

    assert [item.index for item in response.data] == [5, 1, 0]
    assert [item["index"] for item in response.model_dump(exclude_unset=True)["data"]] == [5, 1, 0]
    assert response.usage is None
