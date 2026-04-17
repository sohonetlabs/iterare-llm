"""Tests for merge command."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from iterare_llm.main import app

runner = CliRunner()


class TestMergeCommand:
    @pytest.fixture(autouse=True)
    def setup_patches(self):
        self.patches = [
            patch(
                "iterare_llm.commands.merge.resolve_project_dir",
                return_value=Path("/project"),
            ),
            patch("iterare_llm.commands.merge.is_git_repository", return_value=True),
            patch(
                "iterare_llm.commands.merge.get_current_run", return_value="run-abc123"
            ),
            patch("iterare_llm.commands.merge.branch_exists", return_value=True),
            patch("iterare_llm.commands.merge.get_current_branch", return_value="main"),
            patch("iterare_llm.commands.merge.merge_branch"),
        ]
        self.mocks = {}
        for p in self.patches:
            mock = p.start()
            self.mocks[p.attribute] = mock
        yield
        for p in self.patches:
            p.stop()

    def test_success_most_recent(self):
        result = runner.invoke(app, ["merge"])

        assert result.exit_code == 0
        assert "Successfully merged" in result.output

    def test_success_specific_run(self):
        result = runner.invoke(app, ["merge", "run-abc123"])

        assert result.exit_code == 0

    def test_not_a_git_repo(self):
        self.mocks["is_git_repository"].return_value = False

        result = runner.invoke(app, ["merge"])

        assert result.exit_code == 1
        assert "Not a git repository" in result.output

    def test_no_runs(self):
        self.mocks["get_current_run"].return_value = None

        result = runner.invoke(app, ["merge"])

        assert result.exit_code == 1
        assert "No runs found" in result.output

    def test_branch_does_not_exist(self):
        self.mocks["branch_exists"].return_value = False

        result = runner.invoke(app, ["merge", "gone-run"])

        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_merge_fails(self):
        self.mocks["merge_branch"].side_effect = Exception("conflict")

        result = runner.invoke(app, ["merge"])

        assert result.exit_code == 1
        assert "Error during merge" in result.output

    def test_get_current_branch_fails(self):
        self.mocks["get_current_branch"].side_effect = Exception("detached HEAD")

        result = runner.invoke(app, ["merge"])

        assert result.exit_code == 1
        assert "Unable to determine current branch" in result.output
