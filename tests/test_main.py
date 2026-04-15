"""Tests for CLI entry point."""

from unittest.mock import patch

from typer.testing import CliRunner

from iterare_llm import __version__
from iterare_llm.main import app

runner = CliRunner()


class TestCallback:

    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert __version__ in result.output

    @patch("iterare_llm.main.setup_logging")
    def test_verbose_flag(self, mock_setup_logging):
        runner.invoke(app, ["--verbose", "--version"])

        assert mock_setup_logging.call_args_list == [
            ((), {"verbose": True}),
        ]

    @patch("iterare_llm.main.setup_logging")
    def test_default_not_verbose(self, mock_setup_logging):
        runner.invoke(app, ["--version"])

        assert mock_setup_logging.call_args_list == [
            ((), {"verbose": False}),
        ]
