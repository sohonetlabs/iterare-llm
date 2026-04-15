"""Tests for log command."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from iterare_llm.commands.log import display_log_pretty, display_log_raw, format_stream_json_line
from iterare_llm.main import app

runner = CliRunner()
TEST_FILES = Path(__file__).parent.parent / "test_files"


class TestFormatStreamJsonLine:

    def test_assistant_text(self):
        line = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello world"}]},
        }

        result = format_stream_json_line(line, verbosity=1)

        assert "Hello world" in result.plain

    def test_assistant_tool_use_verbosity_0(self):
        line = {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]},
        }

        result = format_stream_json_line(line, verbosity=0)

        assert result is None

    def test_assistant_tool_use_verbosity_1(self):
        line = {
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"description": "list files"}},
            ]},
        }

        result = format_stream_json_line(line, verbosity=1)

        assert "Bash" in result.plain
        assert "list files" in result.plain

    def test_assistant_tool_use_verbosity_2_with_command(self):
        line = {
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}},
            ]},
        }

        result = format_stream_json_line(line, verbosity=2)

        assert "ls -la" in result.plain

    def test_assistant_tool_use_verbosity_2_raw_input(self):
        line = {
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Edit", "input": {"file": "foo.py"}},
            ]},
        }

        result = format_stream_json_line(line, verbosity=2)

        assert "foo.py" in result.plain

    def test_assistant_tool_use_verbosity_2_description(self):
        line = {
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"description": "run tests"}},
            ]},
        }

        result = format_stream_json_line(line, verbosity=2)

        assert "run tests" in result.plain

    def test_assistant_tool_use_verbosity_2_long_input_truncated(self):
        line = {
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Edit", "input": {"data": "x" * 300}},
            ]},
        }

        result = format_stream_json_line(line, verbosity=2)

        assert "..." in result.plain

    def test_assistant_tool_use_verbosity_1_command(self):
        line = {
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "make test"}},
            ]},
        }

        result = format_stream_json_line(line, verbosity=1)

        assert "make test" in result.plain

    def test_user_tool_result_verbosity_1(self):
        line = {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "output here"}]},
        }

        result = format_stream_json_line(line, verbosity=1)

        assert "output here" in result.plain

    def test_user_tool_result_verbosity_0_skipped(self):
        line = {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "output"}]},
        }

        result = format_stream_json_line(line, verbosity=0)

        assert result is None

    def test_user_tool_result_verbosity_1_truncated(self):
        line = {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "x" * 300}]},
        }

        result = format_stream_json_line(line, verbosity=1)

        assert "..." in result.plain

    def test_user_tool_result_verbosity_2_longer_truncation(self):
        line = {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "x" * 600}]},
        }

        result = format_stream_json_line(line, verbosity=2)

        assert "..." in result.plain

    def test_result_line(self):
        line = {
            "type": "result",
            "duration_ms": 15000,
            "total_cost_usd": 0.1234,
            "num_turns": 5,
        }

        result = format_stream_json_line(line, verbosity=1)

        assert "15.0s" in result.plain
        assert "$0.1234" in result.plain
        assert "5" in result.plain

    def test_error_line(self):
        line = {
            "type": "error",
            "error": {"message": "Something broke"},
        }

        result = format_stream_json_line(line, verbosity=1)

        assert "Something broke" in result.plain

    def test_unknown_type_returns_none(self):
        line = {"type": "unknown"}

        result = format_stream_json_line(line, verbosity=1)

        assert result is None


class TestDisplayLogPretty:

    def test_displays_log(self, capsys):
        display_log_pretty(TEST_FILES / "sample_log.jsonl", verbosity=1, follow=False)

        captured = capsys.readouterr()
        assert "Starting task" in captured.out

    def test_missing_file(self, tmp_path, capsys):
        display_log_pretty(tmp_path / "missing.log", verbosity=1, follow=False)

        captured = capsys.readouterr()
        assert "Log file not found" in captured.out

    def test_blank_lines_and_non_json(self, capsys):
        display_log_pretty(TEST_FILES / "log_with_blanks.jsonl", verbosity=2, follow=False)

        captured = capsys.readouterr()
        assert "Hello" in captured.out
        assert "not json at all" in captured.out


class TestDisplayLogRaw:

    def test_displays_raw(self, capsys):
        display_log_raw(TEST_FILES / "sample_log.jsonl", follow=False)

        captured = capsys.readouterr()
        assert '"type": "assistant"' in captured.out

    def test_missing_file(self, tmp_path, capsys):
        display_log_raw(tmp_path / "missing.log", follow=False)

        captured = capsys.readouterr()
        assert "Log file not found" in captured.out


class TestLogCommand:

    @patch("iterare_llm.commands.log.get_current_run", return_value="run-abc123")
    @patch("iterare_llm.commands.log.get_log_file_path")
    @patch("iterare_llm.commands.log.resolve_project_dir")
    def test_most_recent_run(self, mock_project, mock_log_path, _):
        mock_project.return_value = Path("/project")
        mock_log_path.return_value = TEST_FILES / "sample_log.jsonl"

        result = runner.invoke(app, ["log"])

        assert result.exit_code == 0
        assert "Starting task" in result.output

    @patch("iterare_llm.commands.log.load_runs_metadata", return_value={"run-abc123": {}})
    @patch("iterare_llm.commands.log.get_log_file_path")
    @patch("iterare_llm.commands.log.resolve_project_dir")
    def test_specific_run(self, mock_project, mock_log_path, _):
        mock_project.return_value = Path("/project")
        mock_log_path.return_value = TEST_FILES / "sample_log.jsonl"

        result = runner.invoke(app, ["log", "run-abc123"])

        assert result.exit_code == 0

    @patch("iterare_llm.commands.log.get_current_run", return_value=None)
    @patch("iterare_llm.commands.log.resolve_project_dir", return_value=Path("/project"))
    def test_no_runs(self, _, __):
        result = runner.invoke(app, ["log"])

        assert result.exit_code == 1

    @patch("iterare_llm.commands.log.load_runs_metadata", return_value={})
    @patch("iterare_llm.commands.log.list_runs", return_value=[{"run_name": "other-run"}])
    @patch("iterare_llm.commands.log.resolve_project_dir", return_value=Path("/project"))
    def test_run_not_found(self, _, __, ___):
        result = runner.invoke(app, ["log", "nonexistent"])

        assert result.exit_code == 1
        assert "other-run" in result.output

    @patch("iterare_llm.commands.log.load_runs_metadata", return_value={"run-abc123": {}})
    @patch("iterare_llm.commands.log.get_log_file_path")
    @patch("iterare_llm.commands.log.resolve_project_dir")
    def test_raw_mode(self, mock_project, mock_log_path, _):
        mock_project.return_value = Path("/project")
        mock_log_path.return_value = TEST_FILES / "sample_log.jsonl"

        result = runner.invoke(app, ["log", "--raw", "run-abc123"])

        assert result.exit_code == 0
        assert '"type": "assistant"' in result.output
