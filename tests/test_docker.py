"""Tests for Docker container management."""

import docker.errors
import pytest

from unittest.mock import MagicMock, call

from pathlib import Path
from unittest.mock import patch

from iterare_llm.docker import (
    build_container_config,
    build_volume_mounts,
    container_running,
    ensure_image,
    find_container_by_name,
    generate_container_name,
    generate_domains_file,
    get_docker_client,
    get_image_user,
    image_exists,
    launch_container,
)
from iterare_llm.exceptions import (
    ContainerAlreadyRunningError,
    DockerError,
    ImageNotFoundError,
)


class TestGetDockerClient:
    def test_success(self, mock_docker_client):
        result = get_docker_client()

        assert result is mock_docker_client

    def test_connection_failure(self, mock_docker_client):
        mock_docker_client.ping.side_effect = docker.errors.DockerException(
            "connection refused"
        )

        with pytest.raises(DockerError, match="Failed to connect"):
            get_docker_client()


class TestImageExists:
    def test_exists(self, mock_docker_client):
        result = image_exists(mock_docker_client, "iterare-llm:latest")

        assert result is True

    def test_not_found(self, mock_docker_client):
        mock_docker_client.images.get.side_effect = docker.errors.ImageNotFound("nope")

        result = image_exists(mock_docker_client, "missing:latest")

        assert result is False

    def test_docker_error(self, mock_docker_client):
        mock_docker_client.images.get.side_effect = docker.errors.DockerException(
            "boom"
        )

        with pytest.raises(DockerError, match="Error checking image"):
            image_exists(mock_docker_client, "bad:latest")


class TestEnsureImage:
    def test_exists_locally(self, mock_docker_client):
        ensure_image(mock_docker_client, "iterare-llm:latest")

        assert mock_docker_client.images.pull.call_args_list == []

    def test_pulls_when_not_local(self, mock_docker_client):
        mock_docker_client.images.get.side_effect = docker.errors.ImageNotFound("nope")

        ensure_image(mock_docker_client, "sohonet/iterare-llm:latest")

        assert mock_docker_client.images.pull.call_args_list == [
            call("sohonet/iterare-llm:latest")
        ]

    def test_pull_not_found_in_registry(self, mock_docker_client):
        mock_docker_client.images.get.side_effect = docker.errors.ImageNotFound("nope")
        mock_docker_client.images.pull.side_effect = docker.errors.ImageNotFound("nope")

        with pytest.raises(
            ImageNotFoundError, match="not found locally or in registry"
        ):
            ensure_image(mock_docker_client, "missing:latest")

    def test_pull_api_error(self, mock_docker_client):
        mock_docker_client.images.get.side_effect = docker.errors.ImageNotFound("nope")
        mock_docker_client.images.pull.side_effect = docker.errors.APIError(
            "unauthorized"
        )

        with pytest.raises(DockerError, match="Failed to pull"):
            ensure_image(mock_docker_client, "private/image:latest")


class TestGetImageUser:
    def test_returns_user(self, mock_docker_client):
        image = MagicMock()
        image.attrs = {"Config": {"User": "node"}}
        mock_docker_client.images.get.return_value = image

        result = get_image_user(mock_docker_client, "iterare-llm:latest")

        assert result == "node"

    def test_defaults_to_root(self, mock_docker_client):
        image = MagicMock()
        image.attrs = {"Config": {"User": ""}}
        mock_docker_client.images.get.return_value = image

        result = get_image_user(mock_docker_client, "ubuntu:latest")

        assert result == "root"

    def test_image_not_found(self, mock_docker_client):
        mock_docker_client.images.get.side_effect = docker.errors.ImageNotFound("nope")

        with pytest.raises(ImageNotFoundError):
            get_image_user(mock_docker_client, "missing:latest")

    def test_docker_error(self, mock_docker_client):
        mock_docker_client.images.get.side_effect = docker.errors.DockerException(
            "boom"
        )

        with pytest.raises(DockerError, match="Error inspecting image"):
            get_image_user(mock_docker_client, "bad:latest")


class TestFindContainerByName:
    def test_found(self, mock_docker_client):
        container = MagicMock()
        container.name = "it-task-1"
        mock_docker_client.containers.list.return_value = [container]

        result = find_container_by_name(mock_docker_client, "it-task-1")

        assert result is container

    def test_not_found(self, mock_docker_client):
        mock_docker_client.containers.list.return_value = []

        result = find_container_by_name(mock_docker_client, "it-task-1")

        assert result is None

    def test_partial_name_no_match(self, mock_docker_client):
        container = MagicMock()
        container.name = "it-task-1-extra"
        mock_docker_client.containers.list.return_value = [container]

        result = find_container_by_name(mock_docker_client, "it-task-1")

        assert result is None

    def test_docker_error(self, mock_docker_client):
        mock_docker_client.containers.list.side_effect = docker.errors.DockerException(
            "boom"
        )

        with pytest.raises(DockerError, match="Error searching for container"):
            find_container_by_name(mock_docker_client, "it-task-1")


class TestContainerRunning:
    def test_running(self, mock_docker_client):
        container = MagicMock()
        container.name = "it-task-1"
        container.status = "running"
        mock_docker_client.containers.list.return_value = [container]

        result = container_running(mock_docker_client, "it-task-1")

        assert result is True

    def test_stopped(self, mock_docker_client):
        container = MagicMock()
        container.name = "it-task-1"
        container.status = "exited"
        mock_docker_client.containers.list.return_value = [container]

        result = container_running(mock_docker_client, "it-task-1")

        assert result is False

    def test_not_found(self, mock_docker_client):
        mock_docker_client.containers.list.return_value = []

        result = container_running(mock_docker_client, "it-task-1")

        assert result is False


def test_generate_container_name():
    result = generate_container_name("refactor-api-abc123")

    assert result == "it-refactor-api-abc123"


class TestGenerateDomainsFile:
    @patch("iterare_llm.docker.get_tmp_dir")
    def test_writes_domains(self, mock_tmp_dir, tmp_path):
        mock_tmp_dir.return_value = tmp_path

        result = generate_domains_file(["pypi.org", "example.com"], "run-abc123")

        assert result == tmp_path / "domains-run-abc123.txt"
        assert result.read_text() == "pypi.org\nexample.com\n"

    @patch("iterare_llm.docker.get_tmp_dir")
    def test_empty_domains(self, mock_tmp_dir, tmp_path):
        mock_tmp_dir.return_value = tmp_path

        result = generate_domains_file([], "run-abc123")

        assert result.read_text() == ""

    @patch("iterare_llm.docker.get_tmp_dir")
    def test_os_error(self, mock_tmp_dir):
        mock_tmp_dir.return_value = Path("/nonexistent/readonly/path")

        with pytest.raises(OSError, match="Failed to generate domains file"):
            generate_domains_file(["pypi.org"], "run-abc123")


class TestBuildVolumeMounts:
    @pytest.fixture(autouse=True)
    def setup_files(self, tmp_path):
        self.domains_file = tmp_path / "domains.txt"
        self.domains_file.touch()
        self.log_file = tmp_path / "run.log"
        self.log_file.touch()

    def test_root_user(self, sample_execution_config):
        cfg = sample_execution_config

        result = build_volume_mounts(cfg, "root", self.domains_file, self.log_file)

        assert result == {
            str(cfg.worktree_path): {"bind": "/workspace", "mode": "rw"},
            str(cfg.claude_credentials_path / ".credentials.json"): {
                "bind": "/root/.claude/.credentials.json",
                "mode": "rw",
            },
            str(cfg.claude_config_file): {"bind": "/root/.claude.json", "mode": "rw"},
            str(self.domains_file): {"bind": "/etc/iterare-domains.txt", "mode": "ro"},
            str(self.log_file): {"bind": "/var/log/iterare.log", "mode": "rw"},
        }

    def test_non_root_user(self, sample_execution_config):
        cfg = sample_execution_config

        result = build_volume_mounts(cfg, "node", self.domains_file, self.log_file)

        assert result == {
            str(cfg.worktree_path): {"bind": "/workspace", "mode": "rw"},
            str(cfg.claude_credentials_path / ".credentials.json"): {
                "bind": "/home/node/.claude/.credentials.json",
                "mode": "rw",
            },
            str(cfg.claude_config_file): {
                "bind": "/home/node/.claude.json",
                "mode": "rw",
            },
            str(self.domains_file): {"bind": "/etc/iterare-domains.txt", "mode": "ro"},
            str(self.log_file): {"bind": "/var/log/iterare.log", "mode": "rw"},
        }


class TestBuildContainerConfig:
    @pytest.fixture(autouse=True)
    def setup_files(self, tmp_path):
        self.domains_file = tmp_path / "domains.txt"
        self.domains_file.touch()
        self.log_file = tmp_path / "run.log"
        self.log_file.touch()

    def test_basic_config(self, sample_execution_config):
        result = build_container_config(
            sample_execution_config, "node", self.domains_file, self.log_file
        )

        assert result["image"] == "iterare-llm:latest"
        assert result["name"] == "it-test-run-abc123"
        assert result["detach"] is True
        assert result["auto_remove"] is True
        assert result["working_dir"] == "/workspace"
        assert result["cap_add"] == ["NET_ADMIN"]
        assert "environment" not in result

    def test_with_environment(self, sample_execution_config):
        sample_execution_config.environment = {"PIP_INDEX_URL": "https://pypi.internal"}

        result = build_container_config(
            sample_execution_config, "node", self.domains_file, self.log_file
        )

        assert result["environment"] == {"PIP_INDEX_URL": "https://pypi.internal"}


class TestLaunchContainer:
    @pytest.fixture(autouse=True)
    def setup_paths(self, tmp_path):
        self.tmp_path = tmp_path
        self.patches = [
            patch("iterare_llm.docker.get_tmp_dir", return_value=tmp_path / "tmp"),
            patch(
                "iterare_llm.docker.get_log_file_path",
                return_value=tmp_path / "logs" / "run.log",
            ),
        ]
        for p in self.patches:
            p.start()
        yield
        for p in self.patches:
            p.stop()

    @pytest.fixture
    def ready_client(self, mock_docker_client):
        image = MagicMock()
        image.attrs = {"Config": {"User": "node"}}
        mock_docker_client.images.get.return_value = image
        mock_docker_client.containers.list.return_value = []

        container = MagicMock()
        container.id = "abc123def456"
        mock_docker_client.containers.run.return_value = container

        return mock_docker_client

    def test_success(self, ready_client, sample_execution_config):
        result = launch_container(ready_client, sample_execution_config, "run-abc123")

        assert result == "abc123def456"

    def test_image_not_found_precheck(
        self, mock_docker_client, sample_execution_config
    ):
        mock_docker_client.images.get.side_effect = docker.errors.ImageNotFound("nope")
        mock_docker_client.images.pull.side_effect = docker.errors.ImageNotFound("nope")

        with pytest.raises(ImageNotFoundError):
            launch_container(mock_docker_client, sample_execution_config, "run-abc123")

    def test_container_already_running(
        self, mock_docker_client, sample_execution_config
    ):
        mock_docker_client.images.get.return_value = MagicMock()
        container = MagicMock()
        container.name = "it-test-run-abc123"
        container.status = "running"
        mock_docker_client.containers.list.return_value = [container]

        with pytest.raises(ContainerAlreadyRunningError):
            launch_container(mock_docker_client, sample_execution_config, "run-abc123")

    def test_run_container_error(self, ready_client, sample_execution_config):
        ready_client.containers.run.side_effect = docker.errors.ContainerError(
            "ctr", 1, "cmd", "img", "stderr"
        )

        with pytest.raises(DockerError, match="Container execution failed"):
            launch_container(ready_client, sample_execution_config, "run-abc123")

    def test_run_image_not_found(self, ready_client, sample_execution_config):
        ready_client.containers.run.side_effect = docker.errors.ImageNotFound("gone")

        with pytest.raises(ImageNotFoundError):
            launch_container(ready_client, sample_execution_config, "run-abc123")

    def test_run_api_error(self, ready_client, sample_execution_config):
        ready_client.containers.run.side_effect = docker.errors.APIError("api boom")

        with pytest.raises(DockerError, match="Docker API error"):
            launch_container(ready_client, sample_execution_config, "run-abc123")

    def test_run_docker_exception(self, ready_client, sample_execution_config):
        ready_client.containers.run.side_effect = docker.errors.DockerException(
            "generic"
        )

        with pytest.raises(DockerError, match="Failed to launch container"):
            launch_container(ready_client, sample_execution_config, "run-abc123")
