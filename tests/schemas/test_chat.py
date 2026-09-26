import pytest
from pydantic import ValidationError

from llm_gateway.schemas.chat import Delta, ResponseMessage


@pytest.mark.parametrize("model", [ResponseMessage, Delta])
def test_reasoning_content_is_a_typed_optional_field(model: type[ResponseMessage | Delta]) -> None:
    assert model().reasoning_content is None
    assert model(reasoning_content="Analysis").reasoning_content == "Analysis"
    with pytest.raises(ValidationError):
        model.model_validate({"reasoning_content": ["invalid"]})
