from llm_gateway.guardrails.detectors import Finding
from llm_gateway.guardrails.policy import GuardrailPolicy
from llm_gateway.guardrails.redaction import Redactor, RestoreBuffer
from llm_gateway.guardrails.session import GuardrailSession
from llm_gateway.schemas.chat import ChatCompletionRequest
from tests.guardrails.fixtures import EMAIL


def test_holdback_only_keeps_valid_prefix_and_flushes_at_end() -> None:
    redactor = Redactor()
    redactor.redact(EMAIL, [Finding(0, len(EMAIL), "email")])
    buffer = RestoreBuffer(redactor)

    assert buffer.push("ordinary [x") == "ordinary [x"
    assert buffer.push("[EMA") == ""
    assert buffer.push("IL_1] then [") == EMAIL + " then "
    assert len(buffer.pending) < len("[EMAIL_1]")
    assert buffer.push("", final=True) == "["


def test_substitution_does_not_recursively_restore_originals() -> None:
    redactor = Redactor()
    redactor.originals.update({"[EMAIL_1]": "[EMAIL_2]", "[EMAIL_2]": EMAIL})

    assert redactor.restore("[EMAIL_1]") == "[EMAIL_2]"


def test_request_finalization_releases_restore_mapping() -> None:
    session = GuardrailSession(GuardrailPolicy((("email", "redact"),)))
    request = ChatCompletionRequest.model_validate(
        {"model": "groq/model", "messages": [{"role": "user", "content": EMAIL}]}
    )
    session.protect_input(request)
    assert session.redactor.originals

    session.report()

    assert not session.redactor.originals
    assert not session.redactor.tokens
