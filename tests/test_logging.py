"""Tests for logging configuration."""

import logging

from iterare_llm.logging import get_logger, setup_logging


class TestSetupLogging:

    def test_verbose_sets_debug(self):
        setup_logging(verbose=True)

        assert logging.getLogger().level == logging.DEBUG

    def test_default_sets_info(self):
        setup_logging(verbose=False)

        assert logging.getLogger().level == logging.INFO


class TestGetLogger:

    def test_returns_logger_with_name(self):
        result = get_logger("iterare_llm.git")

        assert isinstance(result, logging.Logger)
        assert result.name == "iterare_llm.git"
