import io
import logging

import pytest

from app.logging_config import configure_application_logging


@pytest.fixture
def app_logger(monkeypatch):
    logger = logging.getLogger("app")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "propagate", True)
    previous_level = logger.level
    yield logger
    logger.setLevel(previous_level)


def test_default_info_child_logs_emit_once_without_resetting_uvicorn(app_logger, monkeypatch):
    monkeypatch.delenv("RESEARCHGUARD_LOG_LEVEL", raising=False)
    monkeypatch.setattr(logging.getLogger(), "handlers", [])
    root_handlers = list(logging.getLogger().handlers)
    uvicorn_handlers = list(logging.getLogger("uvicorn.error").handlers)
    configure_application_logging()
    configure_application_logging()
    assert app_logger.level == logging.INFO
    assert len(app_logger.handlers) == 1
    assert app_logger.propagate is True
    assert logging.getLogger().handlers == root_handlers
    assert logging.getLogger("uvicorn.error").handlers == uvicorn_handlers
    stream = io.StringIO()
    app_logger.handlers[0].setStream(stream)
    child = logging.getLogger("app.researchguard.adapters.paperqa2")
    assert child.isEnabledFor(logging.INFO)
    child.info("paperqa_index_cache_hit source=test-source")
    assert stream.getvalue().count("paperqa_index_cache_hit") == 1


@pytest.mark.parametrize("requested, expected", [("WARNING", logging.WARNING), (" debug ", logging.DEBUG), ("invalid", logging.INFO)])
def test_configurable_level_and_safe_fallback(app_logger, monkeypatch, requested, expected):
    monkeypatch.setenv("RESEARCHGUARD_LOG_LEVEL", requested)
    configure_application_logging()
    assert app_logger.level == expected


def test_existing_app_handler_is_reused(app_logger):
    handler = logging.StreamHandler(io.StringIO())
    app_logger.addHandler(handler)
    configure_application_logging()
    assert app_logger.handlers == [handler]


def test_root_handler_receives_one_record_without_duplicate_fallback(app_logger, monkeypatch):
    root_stream = io.StringIO()
    root_handler = logging.StreamHandler(root_stream)
    monkeypatch.setattr(logging.getLogger(), "handlers", [root_handler])
    configure_application_logging()
    own_stream = io.StringIO()
    app_logger.handlers[0].setStream(own_stream)
    logging.getLogger("app.services.manual_source").info("manual_source_accepted doi=offline-test")
    assert root_stream.getvalue().count("manual_source_accepted") == 1
    assert own_stream.getvalue() == ""
    assert logging.getLogger().handlers == [root_handler]
