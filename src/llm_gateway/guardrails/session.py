"""Request-local actions and metadata; never attach sensitive data to receipts."""

from collections import Counter
from typing import Literal

import structlog
from opentelemetry.trace import Span

from llm_gateway.errors import GatewayError
from llm_gateway.guardrails.detectors import Finding, scan
from llm_gateway.guardrails.policy import Action, Detector, GuardrailPolicy
from llm_gateway.guardrails.redaction import Redactor
from llm_gateway.guardrails.text import transform_text
from llm_gateway.observability.tracing import current, span
from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionRequest
from llm_gateway.schemas.embeddings import EmbeddingRequest

Direction = Literal["input", "output"]


class GuardrailSession:
    def __init__(self, policy: GuardrailPolicy) -> None:
        self.policy = policy
        self.redactor = Redactor()
        self.findings: Counter[tuple[Direction, Detector, Action]] = Counter()
        self.redaction_count = 0
        self.reported = False

    def protect_input[R: (ChatCompletionRequest, EmbeddingRequest)](self, request: R) -> R:
        data = request.model_dump(exclude_unset=True, by_alias=True)
        transform_text(data, self.redactor.reserve)
        with span("guardrails.input") as active:
            blocked: set[Detector] = set()
            data = transform_text(
                data, lambda text: self._inspect(text, "input", self.redactor, blocked)
            )
            self._annotate(active, "input")
            if blocked:
                raise _blocked(blocked, "input")
        return type(request).model_validate(data)

    def protect_output(self, response: ChatCompletion) -> ChatCompletion:
        masker = Redactor(output=True)
        blocked: set[Detector] = set()
        with span("guardrails.output") as active:
            data = transform_text(
                response.model_dump(exclude_unset=True),
                lambda text: self._inspect(text, "output", masker, blocked),
            )
            self._annotate(active, "output")
            if blocked:
                raise _blocked(blocked, "output")
        return ChatCompletion.model_validate(data)

    def restore_output(self, response: ChatCompletion) -> ChatCompletion:
        return ChatCompletion.model_validate(
            transform_text(response.model_dump(exclude_unset=True), self.redactor.restore)
        )

    def detect_stream(self, texts: list[str]) -> None:
        with span("guardrails.output") as active:
            for text in texts:
                for finding in scan(text):
                    self.findings[
                        ("output", finding.detector, self.policy.action(finding.detector))
                    ] += 1
            self._annotate(active, "output")

    def report(self) -> None:
        if self.reported:
            return
        self.reported = True
        counts: Counter[str] = Counter()
        telemetry = current.get()
        for (direction, detector, action), count in self.findings.items():
            counts[detector] += count
            if telemetry is not None:
                telemetry.metrics.guardrail_findings.labels(direction, detector, action).inc(count)
        structlog.get_logger("llm_gateway.guardrails").info(
            "guardrail_findings", counts=dict(counts)
        )
        self.redactor.originals.clear()
        self.redactor.tokens.clear()

    def _inspect(
        self, text: str, direction: Direction, redactor: Redactor, blocked: set[Detector]
    ) -> str:
        redactions: list[Finding] = []
        for finding in scan(text):
            action = self.policy.action(finding.detector)
            self.findings[(direction, finding.detector, action)] += 1
            if action == "block":
                blocked.add(finding.detector)
            elif action == "redact":
                redactions.append(finding)
        changed, count = redactor.redact(text, redactions)
        if direction == "input":
            self.redaction_count += count
        return changed

    def _annotate(self, active: Span, direction: Direction) -> None:
        counts: Counter[str] = Counter()
        for (found_direction, detector, _), count in self.findings.items():
            if found_direction == direction:
                counts[detector] += count
        for detector, count in counts.items():
            active.set_attribute(f"lgw.guardrails.{detector}", count)


def _blocked(detectors: set[Detector], direction: Direction) -> GatewayError:
    return GatewayError(
        400 if direction == "input" else 502,
        "Guardrail blocked detector types: " + ", ".join(sorted(detectors)),
        type="invalid_request_error" if direction == "input" else "upstream_error",
        code="guardrail_blocked" if direction == "input" else "guardrail_blocked_output",
    )
