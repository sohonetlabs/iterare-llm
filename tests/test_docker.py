"""Tests for Docker container management."""

import docker.errors
import pytest

from textwrap import dedent
from unittest.mock import MagicMock, call, ANY

from pathlib import Path
from unittest.mock import patch

from iterare_llm.config import Mount, expand_path
from iterare_llm.docker import (
    NETWORK_SUBNETS_ENV_VAR,
    attach_additional_networks,
    build_container_config,
    build_docker_run_command,
    build_volume_mounts,
    get_docker_network_subnets,
    container_running,
    detect_compose_network,
    docker_network_autocomplete,
    load_compose_file,
    ensure_image,
    find_container_by_name,
    generate_container_name,
    generate_domains_file,
    get_docker_client,
    get_image_user,
    get_network_subnets,
    image_exists,
    launch_container,
    list_docker_networks,
    network_exists,
    get_docker_networks,
    read_dotenv_compose_project_name,
)
from iterare_llm.exceptions import (
    ContainerAlreadyRunningError,
    DockerError,
    ImageNotFoundError,
    NetworkNotFoundError,
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

    def test_extra_mounts_are_included(self, sample_execution_config):
        cfg = sample_execution_config
        cfg.extra_mounts = [
            Mount(source="/host/data", target="/workspace/data", mode="ro")
        ]

        result = build_volume_mounts(cfg, "node", self.domains_file, self.log_file)

        assert result["/host/data"] == {"bind": "/workspace/data", "mode": "ro"}

    def test_extra_mount_source_is_expanded(self, sample_execution_config, tmp_path):
        cfg = sample_execution_config
        with patch.dict("os.environ", {"DATA_DIR": str(tmp_path)}):
            cfg.extra_mounts = [
                Mount(source="$DATA_DIR/data", target="/workspace/data")
            ]

            result = build_volume_mounts(cfg, "node", self.domains_file, self.log_file)

        assert str(tmp_path / "data") in result

    def test_essential_mounts_win_on_conflict(self, sample_execution_config):
        # An extra mount whose source collides with the worktree source must
        # not override the essential /workspace bind.
        cfg = sample_execution_config
        cfg.extra_mounts = [
            Mount(source=str(cfg.worktree_path), target="/somewhere-else", mode="ro")
        ]

        result = build_volume_mounts(cfg, "node", self.domains_file, self.log_file)

        assert result[str(cfg.worktree_path)] == {"bind": "/workspace", "mode": "rw"}


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

    def test_with_network_subnets(self, sample_execution_config):
        sample_execution_config.network_subnets = ["10.0.0.0/24", "172.18.0.0/16"]

        result = build_container_config(
            sample_execution_config, "node", self.domains_file, self.log_file
        )

        assert result["environment"] == {
            NETWORK_SUBNETS_ENV_VAR: "10.0.0.0/24,172.18.0.0/16"
        }

    def test_with_environment_and_subnets(self, sample_execution_config):
        sample_execution_config.environment = {"FOO": "bar"}
        sample_execution_config.network_subnets = ["10.0.0.0/24"]

        result = build_container_config(
            sample_execution_config, "node", self.domains_file, self.log_file
        )

        assert result["environment"] == {
            "FOO": "bar",
            NETWORK_SUBNETS_ENV_VAR: "10.0.0.0/24",
        }

    def test_with_networks(self, sample_execution_config):
        sample_execution_config.networks = ["my-net", "other-net"]

        result = build_container_config(
            sample_execution_config, "node", self.domains_file, self.log_file
        )

        assert result["network"] == "my-net"


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

    def test_attaches_additional_networks(self, ready_client, sample_execution_config):
        sample_execution_config.networks = ["primary", "extra-1", "extra-2"]

        launch_container(ready_client, sample_execution_config, "run-abc123")

        assert ready_client.networks.get.return_value.connect.call_args_list == [
            call(ANY),
            call(ANY),
        ]


class TestNetworkExists:
    def test_found(self, mock_docker_client):
        mock_docker_client.networks.get.return_value = MagicMock()

        assert network_exists(mock_docker_client, "my-net") is True

    def test_not_found(self, mock_docker_client):
        mock_docker_client.networks.get.side_effect = docker.errors.NotFound("nope")

        assert network_exists(mock_docker_client, "missing") is False

    def test_docker_error(self, mock_docker_client):
        mock_docker_client.networks.get.side_effect = docker.errors.DockerException(
            "boom"
        )

        with pytest.raises(DockerError, match="Error inspecting docker network"):
            network_exists(mock_docker_client, "broken")


class TestGetNetworkSubnets:
    def test_returns_subnets(self, mock_docker_client):
        network = MagicMock()
        network.attrs = {
            "IPAM": {
                "Config": [
                    {"Subnet": "172.18.0.0/16"},
                    {"Subnet": "10.0.0.0/24"},
                ]
            }
        }
        mock_docker_client.networks.get.return_value = network

        result = get_network_subnets(mock_docker_client, "my-net")

        assert result == ["172.18.0.0/16", "10.0.0.0/24"]

    def test_no_ipam(self, mock_docker_client):
        network = MagicMock()
        network.attrs = {}
        mock_docker_client.networks.get.return_value = network

        assert get_network_subnets(mock_docker_client, "my-net") == []

    def test_ipam_without_config(self, mock_docker_client):
        network = MagicMock()
        network.attrs = {"IPAM": {"Config": None}}
        mock_docker_client.networks.get.return_value = network

        assert get_network_subnets(mock_docker_client, "my-net") == []

    def test_skips_entries_without_subnet(self, mock_docker_client):
        network = MagicMock()
        network.attrs = {"IPAM": {"Config": [{"Gateway": "10.0.0.1"}]}}
        mock_docker_client.networks.get.return_value = network

        assert get_network_subnets(mock_docker_client, "my-net") == []

    def test_not_found(self, mock_docker_client):
        mock_docker_client.networks.get.side_effect = docker.errors.NotFound("nope")

        with pytest.raises(NetworkNotFoundError):
            get_network_subnets(mock_docker_client, "missing")

    def test_docker_error(self, mock_docker_client):
        mock_docker_client.networks.get.side_effect = docker.errors.DockerException(
            "boom"
        )

        with pytest.raises(DockerError, match="Error inspecting docker network"):
            get_network_subnets(mock_docker_client, "broken")


class TestListDockerNetworks:
    def test_returns_names(self, mock_docker_client):
        net1 = MagicMock()
        net1.name = "bridge"
        net2 = MagicMock()
        net2.name = "my-app_default"
        mock_docker_client.networks.list.return_value = [net1, net2]

        assert list_docker_networks() == ["bridge", "my-app_default"]

    def test_swallows_errors(self):
        with patch(
            "iterare_llm.docker.get_docker_client",
            side_effect=DockerError("not running"),
        ):
            assert list_docker_networks() == []


class TestDockerNetworkAutocomplete:
    @patch("iterare_llm.docker.list_docker_networks")
    def test_filters_by_prefix(self, mock_list):
        mock_list.return_value = ["alpha", "alpha-2", "beta"]

        assert docker_network_autocomplete("alpha") == ["alpha", "alpha-2"]

    @patch("iterare_llm.docker.list_docker_networks")
    def test_no_filter_returns_all(self, mock_list):
        mock_list.return_value = ["alpha", "beta"]

        assert docker_network_autocomplete("") == ["alpha", "beta"]


class TestLoadComposeFile:
    def test_returns_parsed_dict(self, tmp_path):
        compose_file = tmp_path / "compose.yml"
        compose_file.write_text("name: foo\nservices:\n  web: {}\n")

        assert load_compose_file(compose_file) == {
            "name": "foo",
            "services": {"web": {}},
        }

    def test_oserror_returns_empty_dict(self):
        compose_file = MagicMock(spec=Path)
        compose_file.read_text.side_effect = OSError("permission denied")

        assert load_compose_file(compose_file) == {}

    def test_yaml_error_returns_empty_dict(self):
        compose_file = MagicMock(spec=Path)
        compose_file.read_text.return_value = "not: valid: yaml:::"

        assert load_compose_file(compose_file) == {}

    def test_non_dict_root_returns_empty_dict(self):
        compose_file = MagicMock(spec=Path)
        compose_file.read_text.return_value = "- one\n- two\n"

        assert load_compose_file(compose_file) == {}


class TestReadDotenvComposeProjectName:
    def test_no_env_file_returns_none(self, tmp_path):
        assert read_dotenv_compose_project_name(tmp_path) is None

    def test_reads_value(self, tmp_path):
        (tmp_path / ".env").write_text("COMPOSE_PROJECT_NAME=clearview2\n")

        assert read_dotenv_compose_project_name(tmp_path) == "clearview2"

    def test_strips_quotes_and_whitespace(self, tmp_path):
        (tmp_path / ".env").write_text('COMPOSE_PROJECT_NAME = "My App!"\n')

        assert read_dotenv_compose_project_name(tmp_path) == "myapp"

    def test_ignores_comments_and_blank_lines(self, tmp_path):
        (tmp_path / ".env").write_text(
            dedent(
                """\
                # comment

                FOO=bar
                COMPOSE_PROJECT_NAME=alpha
                """
            )
        )

        assert read_dotenv_compose_project_name(tmp_path) == "alpha"

    def test_missing_key_returns_none(self, tmp_path):
        (tmp_path / ".env").write_text("FOO=bar\n")

        assert read_dotenv_compose_project_name(tmp_path) is None

    def test_blank_value_returns_none(self, tmp_path):
        (tmp_path / ".env").write_text("COMPOSE_PROJECT_NAME=\n")

        assert read_dotenv_compose_project_name(tmp_path) is None

    def test_unreadable_env_file_returns_none(self, tmp_path):
        # The file exists (is_file() is True) but reading it fails; the function
        # should swallow the OSError and degrade gracefully to None.
        (tmp_path / ".env").write_text("COMPOSE_PROJECT_NAME=alpha\n")

        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            assert read_dotenv_compose_project_name(tmp_path) is None


class TestDetectComposeNetwork:
    @pytest.fixture(autouse=True)
    def setup_project(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)
        self.tmp_path = tmp_path
        self.project = tmp_path / "myproj"
        self.project.mkdir()

    def write_compose(self, content: str, filename: str = "docker-compose.yml") -> None:
        (self.project / filename).write_text(content)

    def test_no_compose_file(self):
        assert detect_compose_network(self.project) is None

    def test_default_name_from_directory(self):
        custom = self.tmp_path / "MyApp"
        custom.mkdir()
        (custom / "docker-compose.yml").write_text("services: {}\n")

        assert detect_compose_network(custom) == "myapp_default"

    def test_uses_explicit_name_field(self):
        self.write_compose(
            dedent(
                """\
                name: explicit-name
                services: {}
                """
            )
        )

        assert detect_compose_network(self.project) == "explicit-name_default"

    def test_compose_yaml_extension(self):
        self.write_compose("services: {}\n", filename="compose.yaml")

        assert detect_compose_network(self.project) == "myproj_default"

    def test_invalid_yaml_falls_back_to_directory_name(self):
        self.write_compose("not: valid: yaml:::\n")

        assert detect_compose_network(self.project) == "myproj_default"

    def test_non_dict_yaml_root(self):
        self.write_compose(
            dedent(
                """\
                - entry1
                - entry2
                """
            )
        )

        assert detect_compose_network(self.project) == "myproj_default"

    def test_explicit_name_with_uppercase_and_specials(self):
        self.write_compose("name: 'My App!'\n")

        assert detect_compose_network(self.project) == "myapp_default"

    def test_explicit_name_blank_falls_back(self):
        self.write_compose(
            dedent(
                """\
                name: '   '
                services: {}
                """
            )
        )

        assert detect_compose_network(self.project) == "myproj_default"

    def test_empty_directory_name_returns_none(self):
        custom = self.tmp_path / "___"
        custom.mkdir()
        (custom / "docker-compose.yml").write_text("services: {}\n")

        assert detect_compose_network(custom) is None

    def test_dotenv_overrides_directory_name(self):
        self.write_compose("services: {}\n")
        (self.project / ".env").write_text("COMPOSE_PROJECT_NAME=clearview2\n")

        assert detect_compose_network(self.project) == "clearview2_default"

    def test_dotenv_overrides_compose_name_field(self):
        self.write_compose(
            dedent(
                """\
                name: from-file
                services: {}
                """
            )
        )
        (self.project / ".env").write_text("COMPOSE_PROJECT_NAME=from-dotenv\n")

        assert detect_compose_network(self.project) == "from-dotenv_default"

    def test_env_var_overrides_dotenv(self, monkeypatch):
        self.write_compose(
            dedent(
                """\
                name: from-file
                services: {}
                """
            )
        )
        (self.project / ".env").write_text("COMPOSE_PROJECT_NAME=from-dotenv\n")
        monkeypatch.setenv("COMPOSE_PROJECT_NAME", "from-shell")

        assert detect_compose_network(self.project) == "from-shell_default"

    def test_env_var_sanitized(self, monkeypatch):
        self.write_compose("services: {}\n")
        monkeypatch.setenv("COMPOSE_PROJECT_NAME", "My App!")

        assert detect_compose_network(self.project) == "myapp_default"

    def test_blank_env_var_falls_through(self, monkeypatch):
        self.write_compose(
            dedent(
                """\
                name: from-file
                services: {}
                """
            )
        )
        monkeypatch.setenv("COMPOSE_PROJECT_NAME", "   ")

        assert detect_compose_network(self.project) == "from-file_default"


class TestGetDockerNetworks:
    def test_no_networks_no_compose(self, mock_docker_client, tmp_path):
        result = get_docker_networks(mock_docker_client, None, False, tmp_path)

        assert result == []

    def test_explicit_networks_validated(self, mock_docker_client, tmp_path):
        mock_docker_client.networks.get.return_value = MagicMock()

        result = get_docker_networks(
            mock_docker_client, ["net-a", "net-b"], False, tmp_path
        )

        assert result == ["net-a", "net-b"]

    def test_explicit_networks_deduplicated(self, mock_docker_client, tmp_path):
        mock_docker_client.networks.get.return_value = MagicMock()

        result = get_docker_networks(
            mock_docker_client, ["net-a", "net-a", "net-b"], False, tmp_path
        )

        assert result == ["net-a", "net-b"]

    def test_explicit_network_missing_raises(self, mock_docker_client, tmp_path):
        mock_docker_client.networks.get.side_effect = docker.errors.NotFound("nope")

        with pytest.raises(NetworkNotFoundError, match="missing"):
            get_docker_networks(mock_docker_client, ["missing"], False, tmp_path)

    def test_compose_picked_up_only_when_requested(self, mock_docker_client, tmp_path):
        project = tmp_path / "myproj"
        project.mkdir()
        (project / "docker-compose.yml").write_text("services: {}\n")
        mock_docker_client.networks.get.return_value = MagicMock()

        result = get_docker_networks(mock_docker_client, None, True, project)

        assert result == ["myproj_default"]

    def test_compose_not_consulted_by_default(self, mock_docker_client, tmp_path):
        project = tmp_path / "myproj"
        project.mkdir()
        (project / "docker-compose.yml").write_text("services: {}\n")

        result = get_docker_networks(mock_docker_client, None, False, project)

        assert result == []
        # Confirm we didn't even ask Docker about the compose network.
        assert not mock_docker_client.networks.get.called

    def test_compose_inactive_skipped(self, mock_docker_client, tmp_path):
        project = tmp_path / "myproj"
        project.mkdir()
        (project / "docker-compose.yml").write_text("services: {}\n")
        mock_docker_client.networks.get.side_effect = docker.errors.NotFound("nope")

        result = get_docker_networks(mock_docker_client, None, True, project)

        assert result == []

    def test_compose_no_compose_file_logs_and_skips(self, mock_docker_client, tmp_path):
        result = get_docker_networks(mock_docker_client, None, True, tmp_path)

        assert result == []
        assert not mock_docker_client.networks.get.called

    def test_explicit_and_compose_combined(self, mock_docker_client, tmp_path):
        project = tmp_path / "myproj"
        project.mkdir()
        (project / "docker-compose.yml").write_text("services: {}\n")
        mock_docker_client.networks.get.return_value = MagicMock()

        result = get_docker_networks(mock_docker_client, ["net-a"], True, project)

        assert result == ["net-a", "myproj_default"]

    def test_compose_already_in_explicit_not_duplicated(
        self, mock_docker_client, tmp_path
    ):
        project = tmp_path / "myproj"
        project.mkdir()
        (project / "docker-compose.yml").write_text("services: {}\n")
        mock_docker_client.networks.get.return_value = MagicMock()

        result = get_docker_networks(
            mock_docker_client, ["myproj_default"], True, project
        )

        assert result == ["myproj_default"]


class TestGetDockerNetworkSubnets:
    def test_aggregates_and_deduplicates(self, mock_docker_client):
        net_a = MagicMock()
        net_a.attrs = {"IPAM": {"Config": [{"Subnet": "10.0.0.0/24"}]}}
        net_b = MagicMock()
        net_b.attrs = {
            "IPAM": {
                "Config": [
                    {"Subnet": "10.0.0.0/24"},
                    {"Subnet": "172.18.0.0/16"},
                ]
            }
        }
        mock_docker_client.networks.get.side_effect = [net_a, net_b]

        result = get_docker_network_subnets(mock_docker_client, ["a", "b"])

        assert result == ["10.0.0.0/24", "172.18.0.0/16"]

    def test_empty_input(self, mock_docker_client):
        assert get_docker_network_subnets(mock_docker_client, []) == []


class TestAttachAdditionalNetworks:
    def test_noop_when_empty(self, mock_docker_client):
        attach_additional_networks(mock_docker_client, MagicMock(), [])

        assert not mock_docker_client.networks.get.called

    def test_noop_when_single_network(self, mock_docker_client):
        attach_additional_networks(mock_docker_client, MagicMock(), ["only"])

        assert not mock_docker_client.networks.get.called

    def test_connects_extras(self, mock_docker_client):
        net = MagicMock()
        mock_docker_client.networks.get.return_value = net
        container = MagicMock()

        attach_additional_networks(mock_docker_client, container, ["primary", "extra"])

        mock_docker_client.networks.get.assert_called_once_with("extra")
        net.connect.assert_called_once_with(container)

    def test_connect_failure_wrapped(self, mock_docker_client):
        net = MagicMock()
        net.connect.side_effect = docker.errors.DockerException("boom")
        mock_docker_client.networks.get.return_value = net

        with pytest.raises(DockerError, match="Failed to connect"):
            attach_additional_networks(
                mock_docker_client, MagicMock(), ["primary", "extra"]
            )


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

    def test_with_extra_mounts(self):
        result = build_docker_run_command(
            "iterare-llm:latest",
            "it-run",
            self.worktree,
            self.creds,
            self.config_file,
            self.domains_file,
            self.log_file,
            "node",
            extra_mounts=[
                Mount(source="/data", target="/workspace/data", mode="rw"),
                Mount(source="/srv/cache", target="/cache", mode="ro"),
            ],
        )

        # Sources are passed through expand_path (which resolves symlinks), so
        # derive the expected host path the same way rather than hardcoding it.
        assert "-v" in result
        assert f"{expand_path('/data')}:/workspace/data:rw" in result
        assert f"{expand_path('/srv/cache')}:/cache:ro" in result

    def test_extra_mounts_expand_source(self):
        result = build_docker_run_command(
            "iterare-llm:latest",
            "it-run",
            self.worktree,
            self.creds,
            self.config_file,
            self.domains_file,
            self.log_file,
            "node",
            extra_mounts=[
                Mount(source="~/.gitconfig", target="/home/node/.gitconfig", mode="ro")
            ],
        )

        # The leading ~ must be expanded to an absolute host path; the raw "~"
        # must never reach the docker command.
        gitconfig_flags = [
            arg for arg in result if arg.endswith("/home/node/.gitconfig:ro")
        ]
        assert len(gitconfig_flags) == 1
        assert not gitconfig_flags[0].startswith("~")

    def test_extra_mounts_precede_essential_mounts(self):
        result = build_docker_run_command(
            "iterare-llm:latest",
            "it-run",
            self.worktree,
            self.creds,
            self.config_file,
            self.domains_file,
            self.log_file,
            "node",
            extra_mounts=[Mount(source="/data", target="/workspace", mode="rw")],
        )

        # Essential /workspace mount must come AFTER the extra mount so that, on
        # a container-target collision, docker's last-wins rule keeps the
        # worktree mounted (the extra mount can never shadow it).
        idx_extra = result.index(f"{expand_path('/data')}:/workspace:rw")
        idx_workspace = result.index(f"{self.worktree}:/workspace:rw")
        assert idx_extra < idx_workspace

    def test_no_extra_mounts_no_extra_flags(self):
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

        # Only the five essential mounts should be present.
        assert result.count("-v") == 5
