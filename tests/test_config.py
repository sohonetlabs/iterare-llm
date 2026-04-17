"""Tests for configuration loading and validation."""

import shutil
from contextlib import nullcontext as does_not_raise
from pathlib import Path
from unittest.mock import patch

import pytest

from iterare_llm.config import (
    DEFAULT_CREDENTIALS_PATH,
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_SHELL,
    ClaudeConfig,
    DockerConfig,
    build_config_from_dict,
    expand_path,
    get_default_credentials_path,
    parse_toml_config,
    Config,
    FirewallConfig,
    SessionConfig,
    credentials_exist,
    get_claude_credentials_path,
    load_config,
    validate_claude_config,
    validate_credentials,
    validate_config,
    validate_docker_config,
    validate_firewall_config,
)
from iterare_llm.exceptions import ConfigError, CredentialsNotFoundError

TEST_FILES = Path(__file__).parent / "test_files"


@patch(
    "iterare_llm.config.user_config_dir",
    return_value="/home/user/.config/iterare",
)
def test_get_default_credentials_path(mock_user_config_dir):
    result = get_default_credentials_path()

    assert result == "/home/user/.config/iterare"


class TestExpandPath:
    def test_expands_tilde(self):
        result = expand_path("~/some/path")

        assert "~" not in str(result)
        assert result.is_absolute()
        assert str(result).endswith("/some/path")

    def test_expands_env_var(self):
        with patch.dict("os.environ", {"MY_DIR": "/custom/dir"}):
            result = expand_path("$MY_DIR/file.txt")

        assert result == Path("/custom/dir/file.txt")

    def test_absolute_path_unchanged(self):
        result = expand_path("/absolute/path/to/file")

        assert result == Path("/absolute/path/to/file")


class TestParseTomlConfig:
    def test_valid_toml(self):
        result = parse_toml_config(TEST_FILES / "valid_config.toml")

        assert result == {
            "docker": {"image": "my-image:latest"},
            "firewall": {"allowed_domains": ["pypi.org"]},
        }

    def test_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.toml"

        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            parse_toml_config(missing)

    def test_invalid_toml_raises_config_error(self):
        with pytest.raises(ConfigError, match="Invalid TOML syntax"):
            parse_toml_config(TEST_FILES / "invalid_config.toml")

    def test_empty_toml_returns_empty_dict(self):
        result = parse_toml_config(TEST_FILES / "empty_config.toml")

        assert result == {}


class TestBuildConfigFromDict:
    def test_full_dict(self):
        data = {
            "docker": {"image": "custom:v1"},
            "session": {"shell": "/bin/zsh"},
            "claude": {"credentials_path": "/my/creds"},
            "firewall": {"allowed_domains": ["example.com", "pypi.org"]},
        }

        result = build_config_from_dict(data)

        assert result.docker.image == "custom:v1"
        assert result.session.shell == "/bin/zsh"
        assert result.claude.credentials_path == "/my/creds"
        assert result.firewall.allowed_domains == ["example.com", "pypi.org"]

    def test_empty_dict_uses_defaults(self):
        result = build_config_from_dict({})

        assert result.docker.image == DEFAULT_DOCKER_IMAGE
        assert result.session.shell == DEFAULT_SHELL
        assert result.claude.credentials_path == DEFAULT_CREDENTIALS_PATH
        assert result.firewall.allowed_domains == []


class TestValidateDockerConfig:
    def test_valid_image(self):
        config = DockerConfig(image="iterare-llm:latest")

        errors = validate_docker_config(config)

        assert errors == []

    def test_empty_image(self):
        config = DockerConfig(image="")

        errors = validate_docker_config(config)

        assert errors == ["Docker image name cannot be empty"]


class TestValidateClaudeConfig:
    def test_valid_path(self):
        config = ClaudeConfig(credentials_path="/home/user/.config/iterare")

        errors = validate_claude_config(config)

        assert errors == []

    def test_empty_path(self):
        config = ClaudeConfig(credentials_path="")

        errors = validate_claude_config(config)

        assert errors == ["Claude credentials path cannot be empty"]


class TestValidateFirewallConfig:
    def test_valid_domains(self):
        config = FirewallConfig(allowed_domains=["pypi.org", "example.com"])

        errors = validate_firewall_config(config)

        assert errors == []

    def test_empty_list(self):
        config = FirewallConfig(allowed_domains=[])

        errors = validate_firewall_config(config)

        assert errors == []

    def test_not_a_list(self):
        config = FirewallConfig(allowed_domains="pypi.org")

        errors = validate_firewall_config(config)

        assert errors == ["Firewall allowed_domains must be a list"]

    def test_non_string_domain(self):
        config = FirewallConfig(allowed_domains=[123])

        errors = validate_firewall_config(config)

        assert errors == ["Firewall domain must be a string, got: <class 'int'>"]

    def test_whitespace_domain(self):
        config = FirewallConfig(allowed_domains=["  "])

        errors = validate_firewall_config(config)

        assert errors == ["Firewall domain cannot be empty or whitespace"]


class TestValidateConfig:
    def test_valid_config(self):
        config = Config(
            docker=DockerConfig(image="iterare-llm:latest"),
            session=SessionConfig(shell="/bin/bash"),
            claude=ClaudeConfig(credentials_path="/some/path"),
            firewall=FirewallConfig(allowed_domains=["pypi.org"]),
        )

        errors = validate_config(config)

        assert errors == []

    def test_aggregates_errors_from_multiple_validators(self):
        config = Config(
            docker=DockerConfig(image=""),
            session=SessionConfig(shell="/bin/bash"),
            claude=ClaudeConfig(credentials_path=""),
            firewall=FirewallConfig(allowed_domains=["  "]),
        )

        errors = validate_config(config)

        assert len(errors) == 3
        assert "Docker image name cannot be empty" in errors
        assert "Claude credentials path cannot be empty" in errors
        assert "Firewall domain cannot be empty or whitespace" in errors


def test_get_claude_credentials_path(sample_config):
    result = get_claude_credentials_path(sample_config)

    assert isinstance(result, Path)
    assert result.is_absolute()


class TestCredentialsExist:
    def test_existing_directory(self, tmp_path):
        result = credentials_exist(tmp_path)

        assert result is True

    def test_missing_path(self, tmp_path):
        result = credentials_exist(tmp_path / "nope")

        assert result is False

    def test_file_not_directory(self, tmp_path):
        a_file = tmp_path / "not-a-dir"
        a_file.write_text("hi")

        result = credentials_exist(a_file)

        assert result is False


class TestValidateCredentials:
    def test_valid_credentials(self, sample_config):
        with does_not_raise():
            validate_credentials(sample_config)

    def test_missing_credentials_raises(self, tmp_path):
        config = Config(
            docker=DockerConfig(image="img"),
            session=SessionConfig(shell="/bin/bash"),
            claude=ClaudeConfig(credentials_path=str(tmp_path / "nonexistent")),
            firewall=FirewallConfig(allowed_domains=[]),
        )

        with pytest.raises(CredentialsNotFoundError):
            validate_credentials(config)


class TestLoadConfig:
    def test_valid_project(self, project_dir):
        result = load_config(project_dir)

        assert result.docker.image == "iterare-llm:latest"
        assert result.firewall.allowed_domains == ["pypi.org"]

    def test_missing_config_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path)

    def test_invalid_values_raises_config_error(self, tmp_path):
        iterare_dir = tmp_path / ".iterare"
        iterare_dir.mkdir()
        shutil.copy(
            TEST_FILES / "invalid_values_config.toml", iterare_dir / "config.toml"
        )

        with pytest.raises(ConfigError, match="Configuration validation failed"):
            load_config(tmp_path)
