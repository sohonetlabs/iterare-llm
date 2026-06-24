"""Tests for the conversations list command."""

from unittest.mock import patch

import typer
from typer.testing import CliRunner

from iterare_llm.conversations import Conversation
from iterare_llm.main import app

runner = CliRunner()


class TestConversationsCommand:
    @patch("iterare_llm.commands.conversations.list_conversations", return_value=[])
    def test_no_conversations(self, _):
        result = runner.invoke(app, ["conversations"])

        assert result.exit_code == 0
        assert "No conversations found" in result.output

    @patch("iterare_llm.commands.conversations.list_conversations")
    def test_lists_conversations(self, mock_list):
        mock_list.return_value = [
            Conversation("sess-aaaa", "Refactor the API", "main", 1_700_000_000.0),
            Conversation("sess-bbbb", "", "", 1_700_000_100.0),
        ]

        result = runner.invoke(app, ["conversations"])

        assert result.exit_code == 0
        assert "sess-aaaa" in result.output
        assert "Total: 2 conversation(s)" in result.output

    @patch(
        "iterare_llm.commands.conversations.list_conversations",
        side_effect=RuntimeError("boom"),
    )
    def test_unexpected_error_exits(self, _):
        result = runner.invoke(app, ["conversations"])

        assert result.exit_code == 1
        assert "Error" in result.output

    @patch(
        "iterare_llm.commands.conversations.resolve_project_dir",
        side_effect=typer.Exit(2),
    )
    def test_typer_exit_propagates(self, _):
        result = runner.invoke(app, ["conversations"])

        assert result.exit_code == 2
