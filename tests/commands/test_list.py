"""Tests for list command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from iterare_llm.commands.list import display_runs_table, get_run_status
from iterare_llm.main import app

runner = CliRunner()


class TestGetRunStatus:
    def test_active(self):
        docker_client = MagicMock()
        container = MagicMock()
        container.name = "it-run-abc"
        container.status = "running"
        docker_client.containers.list.return_value = [container]

        result = get_run_status("run-abc", Path("/project"), docker_client)

        assert result == "active"

    @patch("iterare_llm.commands.list.worktree_exists", return_value=True)
    def test_finished(self, _, mock_git):
        docker_client = MagicMock()
        docker_client.containers.list.return_value = []

        result = get_run_status("run-abc", Path("/project"), docker_client)

        assert result == "finished"

    @patch("iterare_llm.commands.list.worktree_exists", return_value=False)
    def test_cleaned(self, _, mock_git):
        docker_client = MagicMock()
        docker_client.containers.list.return_value = []

        result = get_run_status("run-abc", Path("/project"), docker_client)

        assert result == "cleaned"


def test_display_runs_table_empty():
    display_runs_table([], "Empty Table")


class TestListCommand:
    @pytest.fixture(autouse=True)
    def setup_patches(self):
        self.patches = [
            patch(
                "iterare_llm.commands.list.resolve_project_dir",
                return_value=Path("/project"),
            ),
            patch("iterare_llm.commands.list.is_git_repository", return_value=True),
            patch("iterare_llm.commands.list.list_runs"),
            patch(
                "iterare_llm.commands.list.get_docker_client", return_value=MagicMock()
            ),
            patch("iterare_llm.commands.list.get_run_status", return_value="finished"),
            patch("iterare_llm.commands.list.worktree_exists", return_value=False),
        ]
        self.mocks = {}
        for p in self.patches:
            mock = p.start()
            self.mocks[p.attribute] = mock
        yield
        for p in self.patches:
            p.stop()

    def test_no_runs(self):
        self.mocks["list_runs"].return_value = []

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "No runs found" in result.output

    def test_with_runs(self):
        self.mocks["list_runs"].return_value = [
            {"run_name": "run-abc", "prompt_name": "task"},
        ]

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "run-abc" in result.output

    def test_not_a_git_repo(self):
        self.mocks["is_git_repository"].return_value = False

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 1
        assert "Not a git repository" in result.output

    def test_all_flag(self):
        self.mocks["list_runs"].return_value = [
            {"run_name": "run-abc", "prompt_name": "task"},
        ]
        self.mocks["get_run_status"].return_value = "cleaned"

        result = runner.invoke(app, ["list", "--all"])

        assert result.exit_code == 0
        assert "run-abc" in result.output

    def test_active_runs(self):
        self.mocks["list_runs"].return_value = [
            {"run_name": "run-abc", "prompt_name": "task"},
        ]
        self.mocks["get_run_status"].return_value = "active"

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "run-abc" in result.output

    def test_docker_unavailable(self):
        from iterare_llm.exceptions import DockerError

        self.mocks["get_docker_client"].side_effect = DockerError("nope")
        self.mocks["list_runs"].return_value = [
            {"run_name": "run-abc", "prompt_name": "task"},
        ]

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0

    def test_docker_unavailable_with_worktree(self):
        from iterare_llm.exceptions import DockerError

        self.mocks["get_docker_client"].side_effect = DockerError("nope")
        self.mocks["worktree_exists"].return_value = True
        self.mocks["list_runs"].return_value = [
            {"run_name": "run-abc", "prompt_name": "task"},
        ]

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "run-abc" in result.output

    def test_unexpected_error(self):
        self.mocks["list_runs"].side_effect = RuntimeError("boom")

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 1
