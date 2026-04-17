"""Tests for workspace preparation."""

import json
from pathlib import Path

import pytest

from iterare_llm.workspace import (
    generate_claude_config,
    prepare_workspace,
    write_claude_config,
    write_prompt_file,
)


def test_generate_claude_config():
    result = generate_claude_config()

    assert result == {
        "dangerouslyDisableToolPermissions": True,
        "maxIterations": 50,
        "workingDirectory": "/workspace",
    }


class TestWriteClaudeConfig:
    def test_writes_json(self, tmp_path):
        config = {"key": "value"}

        write_claude_config(tmp_path, config)

        written = json.loads((tmp_path / ".claude-auto-config.json").read_text())
        assert written == {"key": "value"}

    def test_os_error(self):
        with pytest.raises(OSError, match="Failed to write config file"):
            write_claude_config(Path("/nonexistent/path"), {})


class TestWritePromptFile:
    def test_writes_content(self, tmp_path):
        write_prompt_file(tmp_path, "Do the thing.")

        assert (tmp_path / ".claude-prompt.md").read_text() == "Do the thing."

    def test_os_error(self):
        with pytest.raises(OSError, match="Failed to write prompt file"):
            write_prompt_file(Path("/nonexistent/path"), "content")


class TestPrepareWorkspace:
    def test_creates_both_files(self, tmp_path):
        prepare_workspace(tmp_path, "My prompt content")

        config = json.loads((tmp_path / ".claude-auto-config.json").read_text())
        assert config["dangerouslyDisableToolPermissions"] is True
        assert (tmp_path / ".claude-prompt.md").read_text() == "My prompt content"
