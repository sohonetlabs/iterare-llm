"""Tests for cleanup command."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from iterare_llm.main import app

runner = CliRunner()


class TestCleanupCommand:

    @pytest.fixture(autouse=True)
    def setup_patches(self):
        self.patches = [
            patch("iterare_llm.commands.cleanup.resolve_project_dir", return_value=Path("/project")),
            patch("iterare_llm.commands.cleanup.is_git_repository", return_value=True),
            patch("iterare_llm.commands.cleanup.get_current_run", return_value="run-abc123"),
            patch("iterare_llm.commands.cleanup.worktree_exists", return_value=True),
            patch("iterare_llm.commands.cleanup.branch_exists", return_value=True),
            patch("iterare_llm.commands.cleanup.remove_worktree"),
            patch("iterare_llm.commands.cleanup.remove_branch"),
        ]
        self.mocks = {}
        for p in self.patches:
            mock = p.start()
            self.mocks[p.attribute] = mock
        yield
        for p in self.patches:
            p.stop()

    def test_success_with_yes(self):
        result = runner.invoke(app, ["cleanup", "-y"])

        assert result.exit_code == 0
        assert "Cleanup completed" in result.output

    def test_success_specific_run(self):
        result = runner.invoke(app, ["cleanup", "run-abc123", "-y"])

        assert result.exit_code == 0

    def test_not_a_git_repo(self):
        self.mocks["is_git_repository"].return_value = False

        result = runner.invoke(app, ["cleanup", "-y"])

        assert result.exit_code == 1
        assert "Not a git repository" in result.output

    def test_no_runs(self):
        self.mocks["get_current_run"].return_value = None

        result = runner.invoke(app, ["cleanup", "-y"])

        assert result.exit_code == 1
        assert "No runs found" in result.output

    def test_nothing_to_clean(self):
        self.mocks["worktree_exists"].return_value = False
        self.mocks["branch_exists"].return_value = False

        result = runner.invoke(app, ["cleanup", "-y"])

        assert result.exit_code == 0
        assert "Nothing to clean up" in result.output

    def test_worktree_only(self):
        self.mocks["branch_exists"].return_value = False

        result = runner.invoke(app, ["cleanup", "-y"])

        assert result.exit_code == 0
        assert "Removed worktree" in result.output

    def test_branch_only(self):
        self.mocks["worktree_exists"].return_value = False

        result = runner.invoke(app, ["cleanup", "-y"])

        assert result.exit_code == 0
        assert "Removed branch" in result.output

    def test_confirmation_declined(self):
        result = runner.invoke(app, ["cleanup"], input="n\n")

        assert result.exit_code == 0
        assert "Cleanup cancelled" in result.output

    def test_cleanup_error(self):
        self.mocks["remove_worktree"].side_effect = Exception("git error")

        result = runner.invoke(app, ["cleanup", "-y"])

        assert result.exit_code == 1
        assert "Error during cleanup" in result.output
