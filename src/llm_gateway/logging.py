"""Use one formatter for application, uvicorn and standard-library logs."""

import logging
from typing import Literal

import structlog
from structlog.typing import EventDict, Processor

from llm_gateway.observability.tracing import trace_fields


def configure_logging(level: str, fmt: Literal["json", "console"]) -> None:
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        trace_fields,
        _safe_exception,
    ]
    renderer = (
        structlog.processors.JSONRenderer() if fmt == "json" else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
            keep_exc_info=False,
        )
    )
    root = logging.getLogger()
    # Leave pytest's capture handlers attached; replace only our own prior console handler.
    for existing in root.handlers[:]:
        if isinstance(existing.formatter, structlog.stdlib.ProcessorFormatter):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    # HTTP client debug logs contain URLs; provider URLs are deployment metadata, not telemetry.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _safe_exception(logger: object, method: str, fields: EventDict) -> EventDict:
    """Exception messages and traceback locals can contain request content and secrets."""
    info = fields.pop("exc_info", None)
    if info:
        fields["exception_redacted"] = True
    fields.pop("stack_info", None)
    return fields
