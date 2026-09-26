import pytest
from pydantic import ValidationError

from llm_gateway.schemas.embeddings import EmbeddingRequest


@pytest.mark.parametrize("value", ["one text", ["a", "b"], [1, 2, 3], [[1, 2], [3]]])
def test_embedding_input_shapes(value: object) -> None:
    request = EmbeddingRequest.model_validate({"model": "e", "input": value})

    assert request.to_upstream("gemini") == {"model": "e", "input": value}


@pytest.mark.parametrize("value", ["", [], [""], [[]], [1, "a"], {"text": "x"}])
def test_invalid_embedding_inputs(value: object) -> None:
    with pytest.raises(ValidationError):
        EmbeddingRequest.model_validate({"model": "e", "input": value})
