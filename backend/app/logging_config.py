"""Application logs for portable launches, independent of Uvicorn access logs."""
import logging
import os


class _RootFallbackFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Existing root handlers (including pytest capture) handle propagation.
        # The fallback only emits when they cannot handle this record's level.
        return not any(record.levelno >= handler.level for handler in logging.getLogger().handlers)


def configure_application_logging() -> logging.Logger:
    logger = logging.getLogger("app")
    requested = os.getenv("RESEARCHGUARD_LOG_LEVEL", "INFO").strip().upper()
    level = logging.getLevelNamesMapping().get(requested, logging.INFO)
    logger.setLevel(level)
    # Own the app namespace only. Do not reset Uvicorn or root handlers.
    # Repeated initialization (including reload/import) must not duplicate output.
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        handler.addFilter(_RootFallbackFilter())
        logger.addHandler(handler)
    logger.propagate = True
    return logger
