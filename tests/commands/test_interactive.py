"""Tests for interactive command."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from iterare_llm.commands.interactive import build_docker_run_command
from iterare_llm.exceptions import (
    ContainerAlreadyRunningError,
    ImageNotFoundError,
    IterareError,
    NetworkNotFoundError,
)
from iterare_llm.main import app

runner = CliRunner()


class TestBuildDockerRunCommand:
    @pytest.fixture(autouse=True)
    def setup_paths(self, tmp_path):
        self.worktree = tmp_path / "worktree"
        self.worktree.mkdir()
        self.creds = tmp_path / "creds"
        self.creds.mkdir()
        self.config_file = self.creds / ".claude.json"
        self.config_file.write_text("{}")
        self.domains_file = tmp_path / "domains.txt"
        self.domains_file.touch()
        self.log_file = tmp_path / "run.log"
        self.log_file.touch()

    def test_root_user(self):
        result = build_docker_run_command(
            "iterare-llm:latest",
            "it-run",
            self.worktree,
            self.creds,
            self.config_file,
            self.domains_file,
            self.log_file,
            "root",
        )

        assert result == [
            "docker",
            "run",
            "-it",
            "--rm",
            "--name",
            "it-run",
            "--cap-add",
            "NET_ADMIN",
            "-w",
            "/workspace",
            "-e",
            "ITERARE_MODE=interactive",
            "-v",
            f"{self.worktree}:/workspace:rw",
            "-v",
            f"{self.creds / '.credentials.json'}:/root/.claude/.credentials.json:rw",
            "-v",
            f"{self.config_file}:/root/.claude.json:rw",
            "-v",
            f"{self.domains_file}:/etc/iterare-domains.txt:ro",
            "-v",
            f"{self.log_file}:/var/log/iterare.log:rw",
            "iterare-llm:latest",
        ]

    def test_non_root_user(self):
        result = build_docker_run_command(
            "iterare-llm:latest",
            "it-run",
            self.worktree,
            self.creds,
            self.config_file,
            self.domains_file,
            self.log_file,
            "node",
        )

        assert result == [
            "docker",
            "run",
            "-it",
            "--rm",
            "--name",
            "it-run",
            "--cap-add",
            "NET_ADMIN",
            "-w",
            "/workspace",
            "-e",
            "ITERARE_MODE=interactive",
            "-v",
            f"{self.worktree}:/workspace:rw",
            "-v",
            f"{self.creds / '.credentials.json'}:/home/node/.claude/.credentials.json:rw",
            "-v",
            f"{self.config_file}:/home/node/.claude.json:rw",
            "-v",
            f"{self.domains_file}:/etc/iterare-domains.txt:ro",
            "-v",
            f"{self.log_file}:/var/log/iterare.log:rw",
            "iterare-llm:latest",
        ]

    def test_with_environment_variables(self):
        result = build_docker_run_command(
            "iterare-llm:latest",
            "it-run",
            self.worktree,
            self.creds,
            self.config_file,
            self.domains_file,
            self.log_file,
            "node",
            environment={"MY_VAR": "val"},
        )

        assert result == [
            "docker",
            "run",
            "-it",
            "--rm",
            "--name",
            "it-run",
            "--cap-add",
            "NET_ADMIN",
            "-w",
            "/workspace",
            "-e",
            "ITERARE_MODE=interactive",
            "-e",
            "MY_VAR=val",
            "-v",
            f"{self.worktree}:/workspace:rw",
            "-v",
            f"{self.creds / '.credentials.json'}:/home/node/.claude/.credentials.json:rw",
            "-v",
            f"{self.config_file}:/home/node/.claude.json:rw",
            "-v",
            f"{self.domains_file}:/etc/iterare-domains.txt:ro",
            "-v",
            f"{self.log_file}:/var/log/iterare.log:rw",
            "iterare-llm:latest",
        ]

    def test_with_networks_and_subnets(self):
        result = build_docker_run_command(
            "iterare-llm:latest",
            "it-run",
            self.worktree,
            self.creds,
            self.config_file,
            self.domains_file,
            self.log_file,
            "node",
            networks=["net-a", "net-b"],
            network_subnets=["10.0.0.0/24", "172.18.0.0/16"],
        )

        assert "--network" in result
        assert result.count("--network") == 2
        # Network flags must precede the image argument and follow env flags
        idx_first_network = result.index("--network")
        assert result[idx_first_network + 1] == "net-a"
        assert result[idx_first_network + 3] == "net-b"
        assert "ITERARE_NETWORK_SUBNETS=10.0.0.0/24,172.18.0.0/16" in result

    def test_no_networks_no_flags(self):
        result = build_docker_run_command(
            "iterare-llm:latest",
            "it-run",
            self.worktree,
            self.creds,
            self.config_file,
            self.domains_file,
            self.log_file,
            "node",
            networks=[],
            network_subnets=[],
        )

        assert "--network" not in result
        assert not any("ITERARE_NETWORK_SUBNETS" in arg for arg in result)


class TestInteractiveCommand:
    @pytest.fixture(autouse=True)
    def setup_patches(self, tmp_path):
        self.project_dir = tmp_path
        worktree_path = tmp_path / "workspaces" / "interactive-abc123"
        worktree_path.mkdir(parents=True)
        creds_path = tmp_path / "credentials"
        creds_path.mkdir()
        (creds_path / ".claude.json").write_text("{}")

        log_file = tmp_path / "logs" / "run.log"
        log_file.parent.mkdir(parents=True)
        log_file.touch()

        domains_file = tmp_path / "domains.txt"
        domains_file.touch()

        self.patches = [
            patch(
                "iterare_llm.commands.interactive.resolve_project_dir",
                return_value=tmp_path,
            ),
            patch(
                "iterare_llm.commands.interactive.is_git_repository", return_value=True
            ),
            patch("iterare_llm.commands.interactive.load_config"),
            patch("iterare_llm.commands.interactive.validate_credentials"),
            patch(
                "iterare_llm.commands.interactive.get_docker_client",
                return_value=MagicMock(),
            ),
            patch(
                "iterare_llm.commands.interactive.generate_run_name",
                return_value="interactive-abc123",
            ),
            patch(
                "iterare_llm.commands.interactive.get_current_branch",
                return_value="main",
            ),
            patch("iterare_llm.commands.interactive.validate_launch_requirements"),
            patch(
                "iterare_llm.commands.interactive.create_worktree",
                return_value=worktree_path,
            ),
            patch(
                "iterare_llm.commands.interactive.worktree_exists", return_value=True
            ),
            patch(
                "iterare_llm.commands.interactive.get_worktree_path",
                return_value=worktree_path,
            ),
            patch(
                "iterare_llm.commands.interactive.get_claude_credentials_path",
                return_value=creds_path,
            ),
            patch(
                "iterare_llm.commands.interactive.get_image_user", return_value="node"
            ),
            patch(
                "iterare_llm.commands.interactive.generate_domains_file",
                return_value=domains_file,
            ),
            patch(
                "iterare_llm.commands.interactive.get_log_file_path",
                return_value=log_file,
            ),
            patch(
                "iterare_llm.commands.interactive.generate_container_name",
                return_value="it-interactive-abc123",
            ),
            patch(
                "iterare_llm.commands.interactive.resolve_environment_variables",
                return_value={},
            ),
            patch(
                "iterare_llm.commands.interactive.get_docker_networks",
                return_value=[],
            ),
            patch(
                "iterare_llm.commands.interactive.get_docker_network_subnets",
                return_value=[],
            ),
            patch("iterare_llm.commands.interactive.register_run"),
            patch(
                "iterare_llm.commands.interactive.build_docker_run_command",
                return_value=["docker", "run", "fake"],
            ),
            patch(
                "iterare_llm.commands.interactive.subprocess.run",
                return_value=MagicMock(returncode=0),
            ),
        ]
        self.mocks = {}
        for p in self.patches:
            mock = p.start()
            self.mocks[p.attribute] = mock
        yield
        for p in self.patches:
            p.stop()

    def test_success_no_worktree(self):
        result = runner.invoke(app, ["interactive"])

        assert result.exit_code == 0
        assert "session ended successfully" in result.output

    def test_success_nonzero_exit(self):
        self.mocks["run"].return_value = MagicMock(returncode=1)

        result = runner.invoke(app, ["interactive"])

        assert result.exit_code == 0
        assert "exit code: 1" in result.output

    def test_not_a_git_repo(self):
        self.mocks["is_git_repository"].return_value = False

        result = runner.invoke(app, ["interactive"])

        assert result.exit_code == 1
        assert "Not a git repository" in result.output

    def test_with_worktree(self):
        result = runner.invoke(app, ["interactive", "--worktree"])

        assert result.exit_code == 0

    def test_with_workspace_name(self):
        result = runner.invoke(app, ["interactive", "--workspace", "my-session"])

        assert result.exit_code == 0

    def test_reuse_existing(self):
        result = runner.invoke(app, ["interactive", "--worktree", "--reuse", "old-run"])

        assert result.exit_code == 0

    def test_reuse_missing(self):
        self.mocks["worktree_exists"].return_value = False

        result = runner.invoke(app, ["interactive", "--worktree", "--reuse", "gone"])

        assert result.exit_code == 1
        assert "Cannot reuse" in result.output

    def test_with_env_variables(self):
        self.mocks["resolve_environment_variables"].return_value = {"MY_VAR": "val"}

        result = runner.invoke(app, ["interactive", "--env", "MY_VAR"])

        assert result.exit_code == 0

    def test_image_not_found(self):
        self.mocks["validate_launch_requirements"].side_effect = ImageNotFoundError(
            "missing"
        )

        result = runner.invoke(app, ["interactive"])

        assert result.exit_code == 1

    def test_container_already_running(self):
        self.mocks[
            "validate_launch_requirements"
        ].side_effect = ContainerAlreadyRunningError("busy")

        result = runner.invoke(app, ["interactive"])

        assert result.exit_code == 1
        assert "docker stop" in result.output

    def test_iterare_error(self):
        self.mocks["validate_credentials"].side_effect = IterareError("bad")

        result = runner.invoke(app, ["interactive"])

        assert result.exit_code == 1

    def test_unexpected_error(self):
        self.mocks["run"].side_effect = RuntimeError("boom")

        result = runner.invoke(app, ["interactive"])

        assert result.exit_code == 1
        assert "Unexpected error" in result.output

    def test_keyboard_interrupt(self):
        self.mocks["run"].side_effect = KeyboardInterrupt()

        result = runner.invoke(app, ["interactive"])

        assert result.exit_code == 130

    def test_with_docker_network(self):
        self.mocks["get_docker_networks"].return_value = ["my-net"]
        self.mocks["get_docker_network_subnets"].return_value = ["10.0.0.0/24"]

        result = runner.invoke(app, ["interactive", "--docker-network", "my-net"])

        assert result.exit_code == 0
        kwargs = self.mocks["build_docker_run_command"].call_args.kwargs
        assert kwargs["networks"] == ["my-net"]
        assert kwargs["network_subnets"] == ["10.0.0.0/24"]

    def test_with_docker_network_short_alias(self):
        self.mocks["get_docker_networks"].return_value = ["alias-net"]
        self.mocks["get_docker_network_subnets"].return_value = []

        result = runner.invoke(app, ["interactive", "--dn", "alias-net"])

        assert result.exit_code == 0

    def test_network_not_found(self):
        self.mocks["get_docker_networks"].side_effect = NetworkNotFoundError(
            "Docker network 'gone' does not exist."
        )

        result = runner.invoke(app, ["interactive", "--dn", "gone"])

        assert result.exit_code == 1
        assert "docker network ls" in result.output
