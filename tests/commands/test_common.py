"""Tests for shared command utilities."""

from pathlib import Path

from unittest.mock import patch

import pytest
import typer

from unittest.mock import MagicMock

from iterare_llm.commands.common import (
    cleanup_on_interrupt,
    get_current_run,
    resolve_environment_variables,
    resolve_project_dir,
    run_id_autocomplete,
    run_name_autocomplete,
    validate_launch_requirements,
)
from iterare_llm.config import (
    Config,
    DockerConfig,
    SessionConfig,
    ClaudeConfig,
    FirewallConfig,
)
from iterare_llm.exceptions import ContainerAlreadyRunningError, ImageNotFoundError


class TestResolveProjectDir:
    def test_none_returns_cwd(self):
        result = resolve_project_dir(None)

        assert result == Path.cwd()

    def test_provided_path(self, tmp_path):
        result = resolve_project_dir(tmp_path)

        assert result == tmp_path
        assert result.is_absolute()


class TestRunNameAutocomplete:
    @patch("iterare_llm.commands.common.list_runs")
    def test_filters_by_prefix(self, mock_list_runs):
        mock_list_runs.return_value = [
            {"run_name": "task-abc"},
            {"run_name": "task-def"},
            {"run_name": "other-ghi"},
        ]

        result = run_name_autocomplete("task")

        assert result == ["task-abc", "task-def"]

    @patch("iterare_llm.commands.common.list_runs")
    def test_empty_prefix_returns_all(self, mock_list_runs):
        mock_list_runs.return_value = [
            {"run_name": "task-abc"},
            {"run_name": "other-ghi"},
        ]

        result = run_name_autocomplete("")

        assert result == ["task-abc", "other-ghi"]

    @patch("iterare_llm.commands.common.list_runs", side_effect=Exception("boom"))
    def test_exception_returns_empty(self, _):
        result = run_name_autocomplete("task")

        assert result == []


class TestRunIdAutocomplete:
    @patch("iterare_llm.commands.common.list_runs_with_workspaces")
    def test_filters_by_prefix(self, mock_list):
        mock_list.return_value = ["task-abc", "task-def", "other-ghi"]

        result = run_id_autocomplete("task")

        assert result == ["task-abc", "task-def"]

    @patch("iterare_llm.commands.common.list_runs_with_workspaces")
    def test_empty_prefix_returns_all(self, mock_list):
        mock_list.return_value = ["task-abc", "other-ghi"]

        result = run_id_autocomplete("")

        assert result == ["task-abc", "other-ghi"]

    @patch(
        "iterare_llm.commands.common.list_runs_with_workspaces",
        side_effect=Exception("boom"),
    )
    def test_exception_returns_empty(self, _):
        result = run_id_autocomplete("task")

        assert result == []


class TestGetCurrentRun:
    @patch("iterare_llm.commands.common.list_runs")
    def test_returns_most_recent(self, mock_list_runs):
        mock_list_runs.return_value = [
            {"run_name": "newest"},
            {"run_name": "oldest"},
        ]

        result = get_current_run(Path("/project"))

        assert result == "newest"

    @patch("iterare_llm.commands.common.list_runs", return_value=[])
    def test_no_runs(self, _):
        result = get_current_run(Path("/project"))

        assert result is None


class TestResolveEnvironmentVariables:
    def test_resolves_set_variables(self):
        with patch.dict("os.environ", {"MY_VAR": "my_value", "OTHER": "other_value"}):
            result = resolve_environment_variables(["MY_VAR", "OTHER"])

        assert result == {"MY_VAR": "my_value", "OTHER": "other_value"}

    def test_missing_variable_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(typer.Exit):
                resolve_environment_variables(["MISSING_VAR"])


class TestCleanupOnInterrupt:
    def test_calls_remove_worktree(self, mock_git):
        mock_git.worktree_paths = ["/repo/workspaces/task-1"]

        cleanup_on_interrupt(Path("/repo"), "task-1")

    def test_swallows_exceptions(self, mock_git):
        mock_git.is_repo = False

        cleanup_on_interrupt(Path("/repo"), "task-1")


class TestValidateLaunchRequirements:
    @pytest.fixture
    def config(self):
        return Config(
            docker=DockerConfig(image="iterare-llm:latest"),
            session=SessionConfig(shell="/bin/bash"),
            claude=ClaudeConfig(credentials_path="/creds"),
            firewall=FirewallConfig(allowed_domains=[]),
        )

    def test_passes(self, config, mock_docker_client):
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        validate_launch_requirements(config, mock_docker_client, "task-1")

    def test_image_not_found(self, config, mock_docker_client):
        import docker.errors

        mock_docker_client.images.get.side_effect = docker.errors.ImageNotFound("nope")
        mock_docker_client.images.pull.side_effect = docker.errors.ImageNotFound("nope")

        with pytest.raises(ImageNotFoundError):
            validate_launch_requirements(config, mock_docker_client, "task-1")

    def test_container_already_running(self, config, mock_docker_client):
        mock_docker_client.images.get.return_value = MagicMock()
        container = MagicMock()
        container.name = "it-task-1"
        container.status = "running"
        mock_docker_client.containers.list.return_value = [container]

        with pytest.raises(ContainerAlreadyRunningError):
            validate_launch_requirements(config, mock_docker_client, "task-1")
