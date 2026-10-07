"""
app/config/logging_config.py
────────────────────────────
Structured JSON logging via structlog.
Includes stdlib fallback for environments where structlog is not yet installed.
Every pipeline step gets a consistent, queryable log entry.
"""
import logging
import sys

try:
    import structlog
    _HAS_STRUCTLOG = True
except ImportError:
    structlog = None
    _HAS_STRUCTLOG = False


class _StdlibBoundLogger:
    """Fallback logger wrapper with structlog-compatible kwargs interface."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _format(self, msg: str, kwargs: dict) -> str:
        if kwargs:
            extra = " ".join(f"{k}={v!r}" for k, v in kwargs.items())
            return f"{msg} | {extra}"
        return msg

    def debug(self, msg: str, *args, **kwargs):
        self._logger.debug(self._format(msg, kwargs), *args)

    def info(self, msg: str, *args, **kwargs):
        self._logger.info(self._format(msg, kwargs), *args)

    def warning(self, msg: str, *args, **kwargs):
        self._logger.warning(self._format(msg, kwargs), *args)

    def error(self, msg: str, *args, **kwargs):
        self._logger.error(self._format(msg, kwargs), *args)

    def exception(self, msg: str, *args, **kwargs):
        self._logger.exception(self._format(msg, kwargs), *args)

    def critical(self, msg: str, *args, **kwargs):
        self._logger.critical(self._format(msg, kwargs), *args)


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for structured output, or stdlib logging if structlog is absent."""
    if _HAS_STRUCTLOG:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer() if log_level == "DEBUG"
                else structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, log_level.upper(), logging.INFO)
            ),
            logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
            cache_logger_on_first_use=True,
        )
    else:
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout,
        )


def get_logger(name: str):
    if _HAS_STRUCTLOG:
        return structlog.get_logger(name)
    return _StdlibBoundLogger(logging.getLogger(name))
