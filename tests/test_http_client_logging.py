"""HTTP client request lines never reach the journal.

Guacamole takes its admin token in the query string, and httpx logs the full
request URL at INFO. The deployed hub logs at INFO, so every Guacamole call
wrote a live token to the journal.
"""

from __future__ import annotations

import logging

import pytest

import main


@pytest.mark.parametrize("level", ["INFO", "DEBUG"])
def test_http_client_loggers_stay_at_warning(monkeypatch, level):
    monkeypatch.setenv("SYBR_HUB_LOG_LEVEL", level)
    for name in ("httpx", "httpcore"):
        monkeypatch.setattr(logging.getLogger(name), "level", logging.NOTSET)

    main.configure_logging()

    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        assert not logger.isEnabledFor(logging.INFO)
        assert logger.isEnabledFor(logging.WARNING)


def test_a_request_line_with_a_token_is_not_emitted(monkeypatch, caplog):
    monkeypatch.setenv("SYBR_HUB_LOG_LEVEL", "INFO")
    main.configure_logging()

    with caplog.at_level(logging.INFO):
        logging.getLogger("httpx").info(
            'HTTP Request: DELETE http://guac/api/session/data/x?token=SECRET "HTTP/1.1 204"'
        )

    assert "SECRET" not in caplog.text
