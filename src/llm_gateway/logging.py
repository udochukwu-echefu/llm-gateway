import logging
from typing import Literal

import structlog
from structlog.typing import Processor


def configure_logging(level: str, fmt: Literal["json", "console"]) -> None:
    """One JSON object per line in production; readable output locally.

    Request-scoped fields (request_id, model, ...) are bound with structlog's contextvars,
    so every log line emitted while handling a request carries them automatically.
    """
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    renderer: list[Processor] = (
        [structlog.processors.dict_tracebacks, structlog.processors.JSONRenderer()]
        if fmt == "json"
        else [structlog.dev.ConsoleRenderer()]
    )
    structlog.configure(
        processors=[*shared, *renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,  # keeps structlog.testing.capture_logs working
    )
