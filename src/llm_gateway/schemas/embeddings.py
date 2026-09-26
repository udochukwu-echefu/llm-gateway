from typing import Annotated, Literal

from pydantic import Field

from llm_gateway.schemas.common import ProxiedRequest, ResponseModel

MAX_INPUTS = 2048

# One text, many texts, or the same as already-tokenized integer IDs.
EmbeddingInput = (
    Annotated[str, Field(min_length=1)]
    | Annotated[
        list[Annotated[str, Field(min_length=1)]], Field(min_length=1, max_length=MAX_INPUTS)
    ]
    | Annotated[list[int], Field(min_length=1)]
    | Annotated[
        list[Annotated[list[int], Field(min_length=1)]], Field(min_length=1, max_length=MAX_INPUTS)
    ]
)


class EmbeddingRequest(ProxiedRequest):
    model: str = Field(min_length=1, max_length=256)
    input: EmbeddingInput
    encoding_format: Literal["float", "base64"] | None = None
    dimensions: int | None = Field(default=None, ge=1)
    user: str | None = Field(default=None, max_length=256)


class Embedding(ResponseModel):
    object: str = "embedding"
    index: int
    embedding: list[float] | str  # a string when encoding_format is base64


class EmbeddingUsage(ResponseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(ResponseModel):
    object: str = "list"
    data: list[Embedding]
    model: str
    usage: EmbeddingUsage | None = None
