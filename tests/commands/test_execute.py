"""Tests for execute command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from iterare_llm.commands.execute import (
    display_success_message,
    prompt_name_autocomplete,
)
from iterare_llm.exceptions import (
    ContainerAlreadyRunningError,
    CredentialsNotFoundError,
    ImageNotFoundError,
    IterareError,
    NetworkNotFoundError,
)
from iterare_llm.main import app

runner = CliRunner()


def test_display_success_message(capsys):
    display_success_message(
        "run-abc123", "containerid", Path("/project/workspaces/run-abc123"), "main"
    )

    captured = capsys.readouterr()
    assert "run-abc123" in captured.out
    assert "main" in captured.out


class TestPromptNameAutocomplete:
    @patch("iterare_llm.commands.execute.list_prompts")
    def test_filters_by_prefix(self, mock_list_prompts):
        mock_list_prompts.return_value = [
            Path("alpha.md"),
            Path("alpha-2.md"),
            Path("beta.md"),
        ]

        result = prompt_name_autocomplete("alpha")

        assert result == ["alpha", "alpha-2"]

    @patch("iterare_llm.commands.execute.list_prompts", side_effect=Exception("boom"))
    def test_exception_returns_empty(self, _):
        result = prompt_name_autocomplete("anything")

        assert result == []


class TestExecuteCommand:
    @pytest.fixture(autouse=True)
    def setup_patches(self, tmp_path):
        self.project_dir = tmp_path
        worktree_path = tmp_path / "workspaces" / "task-abc123"
        worktree_path.mkdir(parents=True)
        creds_path = tmp_path / "credentials"
        creds_path.mkdir()
        (creds_path / ".claude.json").write_text("{}")

        prompt_path = tmp_path / ".iterare" / "prompts" / "task.md"
        prompt_path.parent.mkdir(parents=True)
        prompt_path.write_text("Do the thing.")

        self.patches = [
            patch(
                "iterare_llm.commands.execute.resolve_project_dir",
                return_value=tmp_path,
            ),
            patch("iterare_llm.commands.execute.is_git_repository", return_value=True),
            patch("iterare_llm.commands.execute.load_config"),
            patch("iterare_llm.commands.execute.validate_credentials"),
            patch(
                "iterare_llm.commands.execute.resolve_prompt_path",
                return_value=prompt_path,
            ),
            patch("iterare_llm.commands.execute.parse_prompt_file"),
            patch(
                "iterare_llm.commands.execute.get_workspace_name_from_prompt",
                return_value="task",
            ),
            patch(
                "iterare_llm.commands.execute.generate_run_name",
                return_value="task-abc123",
            ),
            patch(
                "iterare_llm.commands.execute.get_current_branch", return_value="main"
            ),
            patch(
                "iterare_llm.commands.execute.get_docker_client",
                return_value=MagicMock(),
            ),
            patch("iterare_llm.commands.execute.validate_launch_requirements"),
            patch(
                "iterare_llm.commands.execute.create_worktree",
                return_value=worktree_path,
            ),
            patch("iterare_llm.commands.execute.worktree_exists", return_value=True),
            patch(
                "iterare_llm.commands.execute.get_worktree_path",
                return_value=worktree_path,
            ),
            patch("iterare_llm.commands.execute.prepare_workspace"),
            patch(
                "iterare_llm.commands.execute.resolve_environment_variables",
                return_value={},
            ),
            patch(
                "iterare_llm.commands.execute.get_docker_networks",
                return_value=[],
            ),
            patch(
                "iterare_llm.commands.execute.get_docker_network_subnets",
                return_value=[],
            ),
            patch(
                "iterare_llm.commands.execute.get_claude_credentials_path",
                return_value=creds_path,
            ),
            patch(
                "iterare_llm.commands.execute.launch_container",
                return_value="containerid123",
            ),
            patch("iterare_llm.commands.execute.register_run"),
        ]
        self.mocks = {}
        for p in self.patches:
            mock = p.start()
            self.mocks[p.attribute] = mock
        yield
        for p in self.patches:
            p.stop()

    def test_success(self):
        result = runner.invoke(app, ["execute", "task"])

        assert result.exit_code == 0
        assert "containerid123" in result.output

    def test_not_a_git_repo(self):
        self.mocks["is_git_repository"].return_value = False

        result = runner.invoke(app, ["execute", "task"])

        assert result.exit_code == 1
        assert "Not a git repository" in result.output

    def test_image_not_found(self):
        self.mocks["validate_launch_requirements"].side_effect = ImageNotFoundError(
            "missing"
        )

        result = runner.invoke(app, ["execute", "task"])

        assert result.exit_code == 1

    def test_container_already_running(self):
        self.mocks[
            "validate_launch_requirements"
        ].side_effect = ContainerAlreadyRunningError("busy")

        result = runner.invoke(app, ["execute", "task"])

        assert result.exit_code == 1
        assert "docker stop" in result.output

    def test_credentials_not_found(self):
        self.mocks["validate_credentials"].side_effect = CredentialsNotFoundError(
            "missing"
        )

        result = runner.invoke(app, ["execute", "task"])

        assert result.exit_code == 1

    def test_iterare_error(self):
        self.mocks["launch_container"].side_effect = IterareError("failed")

        result = runner.invoke(app, ["execute", "task"])

        assert result.exit_code == 1

    def test_unexpected_error(self):
        self.mocks["launch_container"].side_effect = RuntimeError("boom")

        result = runner.invoke(app, ["execute", "task"])

        assert result.exit_code == 1
        assert "Unexpected error" in result.output

    def test_keyboard_interrupt(self):
        self.mocks["launch_container"].side_effect = KeyboardInterrupt()

        result = runner.invoke(app, ["execute", "task"])

        assert result.exit_code == 130

    def test_reuse_existing_workspace(self):
        result = runner.invoke(app, ["execute", "task", "--reuse", "old-run"])

        assert result.exit_code == 0

    def test_reuse_missing_workspace(self):
        self.mocks["worktree_exists"].return_value = False

        result = runner.invoke(app, ["execute", "task", "--reuse", "gone"])

        assert result.exit_code == 1
        assert "Cannot reuse" in result.output

    def test_with_env_variables(self):
        self.mocks["resolve_environment_variables"].return_value = {"MY_VAR": "val"}

        result = runner.invoke(app, ["execute", "task", "--env", "MY_VAR"])

        assert result.exit_code == 0

    def test_with_docker_network(self):
        self.mocks["get_docker_networks"].return_value = ["my-net"]
        self.mocks["get_docker_network_subnets"].return_value = ["10.0.0.0/24"]

        result = runner.invoke(app, ["execute", "task", "--docker-network", "my-net"])

        assert result.exit_code == 0
        # use_compose stays False unless --dc is given
        call_args = self.mocks["get_docker_networks"].call_args.args
        assert call_args[1] == ["my-net"]
        assert call_args[2] is False
        exec_config = self.mocks["launch_container"].call_args.args[1]
        assert exec_config.networks == ["my-net"]
        assert exec_config.network_subnets == ["10.0.0.0/24"]

    def test_with_docker_network_short_alias(self):
        self.mocks["get_docker_networks"].return_value = ["alias-net"]

        result = runner.invoke(app, ["execute", "task", "--dn", "alias-net"])

        assert result.exit_code == 0

    def test_with_docker_compose_flag(self):
        self.mocks["get_docker_networks"].return_value = ["myproj_default"]

        result = runner.invoke(app, ["execute", "task", "--docker-compose"])

        assert result.exit_code == 0
        call_args = self.mocks["get_docker_networks"].call_args.args
        assert call_args[1] is None
        assert call_args[2] is True

    def test_with_docker_compose_short_alias(self):
        self.mocks["get_docker_networks"].return_value = ["myproj_default"]

        result = runner.invoke(app, ["execute", "task", "--dc"])

        assert result.exit_code == 0
        assert self.mocks["get_docker_networks"].call_args.args[2] is True

    def test_with_dn_and_dc_combined(self):
        self.mocks["get_docker_networks"].return_value = [
            "my-net",
            "myproj_default",
        ]

        result = runner.invoke(app, ["execute", "task", "--dn", "my-net", "--dc"])

        assert result.exit_code == 0
        call_args = self.mocks["get_docker_networks"].call_args.args
        assert call_args[1] == ["my-net"]
        assert call_args[2] is True

    def test_network_not_found(self):
        self.mocks["get_docker_networks"].side_effect = NetworkNotFoundError(
            "Docker network 'gone' does not exist."
        )

        result = runner.invoke(app, ["execute", "task", "--dn", "gone"])

        assert result.exit_code == 1
        assert "docker network ls" in result.output
