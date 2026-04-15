"""Tests for run name generation and management."""

from pathlib import Path
from unittest.mock import patch

import json

import pytest

from iterare_llm.run import (
    generate_run_name,
    get_runs_file,
    load_runs_metadata,
    list_runs,
    list_runs_with_workspaces,
    register_run,
    save_runs_metadata,
)

TEST_FILES = Path(__file__).parent / "test_files"


class TestGenerateRunName:

    def test_format(self):
        result = generate_run_name("refactor-api")

        assert result.startswith("refactor-api-")
        hash_part = result.split("-")[-1]
        assert len(hash_part) == 8

    def test_unique(self):
        a = generate_run_name("task")
        b = generate_run_name("task")

        assert a != b


class TestGetRunsFile:

    @patch("iterare_llm.run.get_app_cache_dir")
    def test_returns_json_in_runs_dir(self, mock_cache_dir, tmp_path):
        mock_cache_dir.return_value = tmp_path

        result = get_runs_file(Path("/some/project"))

        assert result.parent == tmp_path / "runs"
        assert result.suffix == ".json"
        assert result.name.startswith("runs-")

    @patch("iterare_llm.run.get_app_cache_dir")
    def test_different_projects_get_different_files(self, mock_cache_dir, tmp_path):
        mock_cache_dir.return_value = tmp_path

        a = get_runs_file(Path("/project-a"))
        b = get_runs_file(Path("/project-b"))

        assert a != b


class TestLoadRunsMetadata:

    @patch("iterare_llm.run.get_runs_file")
    def test_no_file(self, mock_get_runs_file, tmp_path):
        mock_get_runs_file.return_value = tmp_path / "nonexistent.json"

        result = load_runs_metadata(Path("/project"))

        assert result == {}

    @patch("iterare_llm.run.get_runs_file")
    def test_valid_file(self, mock_get_runs_file):
        mock_get_runs_file.return_value = TEST_FILES / "valid_runs.json"

        result = load_runs_metadata(Path("/project"))

        assert result == {"run-abc": {"prompt_name": "task"}}

    @patch("iterare_llm.run.get_runs_file")
    def test_corrupt_json(self, mock_get_runs_file):
        mock_get_runs_file.return_value = TEST_FILES / "corrupt_runs.json"

        result = load_runs_metadata(Path("/project"))

        assert result == {}


class TestSaveRunsMetadata:

    @patch("iterare_llm.run.get_runs_file")
    def test_writes_json(self, mock_get_runs_file, tmp_path):
        runs_file = tmp_path / "runs" / "runs.json"
        runs_file.parent.mkdir(parents=True)
        mock_get_runs_file.return_value = runs_file
        metadata = {"run-abc": {"prompt_name": "task"}}

        save_runs_metadata(Path("/project"), metadata)

        assert json.loads(runs_file.read_text()) == metadata

    @patch("iterare_llm.run.get_runs_file")
    def test_os_error(self, mock_get_runs_file):
        mock_get_runs_file.return_value = Path("/nonexistent/dir/runs.json")

        with pytest.raises(OSError, match="Failed to save runs metadata"):
            save_runs_metadata(Path("/project"), {})


@patch("iterare_llm.run.get_app_cache_dir")
def test_register_run(mock_cache_dir, tmp_path):
    mock_cache_dir.return_value = tmp_path

    register_run(Path("/project"), "task-abc123", "task")

    metadata = load_runs_metadata(Path("/project"))
    assert "task-abc123" in metadata
    assert metadata["task-abc123"]["prompt_name"] == "task"
    assert "timestamp" in metadata["task-abc123"]
    assert "project_dir" in metadata["task-abc123"]


class TestListRuns:

    @patch("iterare_llm.run.get_app_cache_dir")
    def test_empty(self, mock_cache_dir, tmp_path):
        mock_cache_dir.return_value = tmp_path

        result = list_runs(Path("/project"))

        assert result == []

    @patch("iterare_llm.run.get_runs_file")
    def test_sorted_newest_first(self, mock_get_runs_file):
        mock_get_runs_file.return_value = TEST_FILES / "runs_multiple.json"

        result = list_runs(Path("/project"))

        assert result[0]["run_name"] == "new-run"
        assert result[1]["run_name"] == "old-run"


class TestListRunsWithWorkspaces:

    @patch("iterare_llm.run.worktree_exists")
    @patch("iterare_llm.run.get_runs_file")
    def test_filters_to_existing_worktrees(self, mock_get_runs_file, mock_worktree_exists):
        mock_get_runs_file.return_value = TEST_FILES / "runs_multiple.json"
        mock_worktree_exists.side_effect = lambda _dir, name: name == "new-run"

        result = list_runs_with_workspaces(Path("/project"))

        assert result == ["new-run"]

    @patch("iterare_llm.run.worktree_exists")
    @patch("iterare_llm.run.get_runs_file")
    def test_none_exist(self, mock_get_runs_file, mock_worktree_exists):
        mock_get_runs_file.return_value = TEST_FILES / "runs_multiple.json"
        mock_worktree_exists.return_value = False

        result = list_runs_with_workspaces(Path("/project"))

        assert result == []
