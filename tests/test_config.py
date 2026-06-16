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
    Mount,
    MountsConfig,
    build_config_from_dict,
    expand_path,
    get_default_credentials_path,
    get_global_config_path,
    merge_config_dicts,
    parse_mount_spec,
    parse_toml_config,
    Config,
    FirewallConfig,
    SessionConfig,
    credentials_exist,
    get_claude_credentials_path,
    load_config,
    load_toml_if_exists,
    validate_claude_config,
    validate_credentials,
    validate_config,
    validate_docker_config,
    validate_firewall_config,
    validate_mounts_config,
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


def test_get_global_config_path():
    result = get_global_config_path()

    assert result == Path.home() / ".iterare" / "config.toml"


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
        assert result.mounts.volumes == []


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
            mounts=MountsConfig(volumes=[]),
        )

        errors = validate_config(config)

        assert errors == []

    def test_aggregates_errors_from_multiple_validators(self):
        config = Config(
            docker=DockerConfig(image=""),
            session=SessionConfig(shell="/bin/bash"),
            claude=ClaudeConfig(credentials_path=""),
            firewall=FirewallConfig(allowed_domains=["  "]),
            mounts=MountsConfig(volumes=[]),
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
            mounts=MountsConfig(volumes=[]),
        )

        with pytest.raises(CredentialsNotFoundError):
            validate_credentials(config)


class TestParseMountSpec:
    def test_source_target_mode(self):
        result = parse_mount_spec("~/.gitconfig:/home/node/.gitconfig:ro")

        assert result == Mount(
            source="~/.gitconfig", target="/home/node/.gitconfig", mode="ro"
        )

    def test_source_target_defaults_to_rw(self):
        result = parse_mount_spec("/data:/workspace/data")

        assert result == Mount(source="/data", target="/workspace/data", mode="rw")

    def test_explicit_rw_mode(self):
        result = parse_mount_spec("/data:/workspace/data:rw")

        assert result.mode == "rw"

    def test_unknown_trailing_segment_is_not_a_mode(self):
        # A third segment that is not a recognised mode is treated as the
        # target, leaving the default mode in place.
        result = parse_mount_spec("/a:/b:/c")

        assert result == Mount(source="/a:/b", target="/c", mode="rw")

    def test_missing_target_raises(self):
        with pytest.raises(ConfigError, match="Invalid mount specification"):
            parse_mount_spec("/only-source")

    def test_empty_source_raises(self):
        with pytest.raises(ConfigError, match="empty source"):
            parse_mount_spec(":/target")

    def test_empty_target_raises(self):
        # "/source:" splits to a non-empty source and an empty target.
        with pytest.raises(ConfigError, match="empty target"):
            parse_mount_spec("/source:")

    def test_non_string_raises(self):
        with pytest.raises(ConfigError, match="must be a string"):
            parse_mount_spec(123)


class TestMergeConfigDicts:
    def test_override_replaces_scalar(self):
        result = merge_config_dicts(
            {"docker": {"image": "global"}}, {"docker": {"image": "project"}}
        )

        assert result == {"docker": {"image": "project"}}

    def test_override_replaces_list_wholesale(self):
        result = merge_config_dicts(
            {"firewall": {"allowed_domains": ["a", "b"]}},
            {"firewall": {"allowed_domains": ["c"]}},
        )

        assert result == {"firewall": {"allowed_domains": ["c"]}}

    def test_falls_through_when_override_absent(self):
        result = merge_config_dicts(
            {"docker": {"image": "global"}, "session": {"shell": "/bin/zsh"}},
            {"docker": {"image": "project"}},
        )

        assert result == {
            "docker": {"image": "project"},
            "session": {"shell": "/bin/zsh"},
        }

    def test_merges_keys_within_a_section(self):
        result = merge_config_dicts(
            {"docker": {"image": "global"}},
            {"docker": {"unrelated": "x"}},
        )

        assert result == {"docker": {"image": "global", "unrelated": "x"}}

    def test_non_table_section_follows_override_wins(self):
        # A top-level value that is not a table (unexpected, but defensible)
        # cannot be merged key-by-key, so override wins; when override lacks it,
        # the base value falls through.
        assert merge_config_dicts({"weird": "base"}, {"weird": "proj"}) == {
            "weird": "proj"
        }
        assert merge_config_dicts({"weird": "base"}, {}) == {"weird": "base"}


class TestBuildMountsFromDict:
    def test_parses_volumes(self):
        data = {"mounts": {"volumes": ["~/.aws:/home/node/.aws:ro"]}}

        result = build_config_from_dict(data)

        assert result.mounts.volumes == [
            Mount(source="~/.aws", target="/home/node/.aws", mode="ro")
        ]


class TestValidateMountsConfig:
    def test_valid_mounts(self):
        config = MountsConfig(volumes=[Mount(source="~/x", target="/x", mode="ro")])

        assert validate_mounts_config(config) == []

    def test_relative_target_rejected(self):
        config = MountsConfig(volumes=[Mount(source="~/x", target="x", mode="ro")])

        errors = validate_mounts_config(config)

        assert any("absolute path" in e for e in errors)

    def test_bad_mode_rejected(self):
        config = MountsConfig(volumes=[Mount(source="~/x", target="/x", mode="z")])

        errors = validate_mounts_config(config)

        assert any("Mount mode must be one of" in e for e in errors)

    def test_empty_source_rejected(self):
        config = MountsConfig(volumes=[Mount(source="  ", target="/x", mode="ro")])

        errors = validate_mounts_config(config)

        assert any("Mount source cannot be empty" in e for e in errors)

    def test_empty_target_rejected(self):
        config = MountsConfig(volumes=[Mount(source="~/x", target="  ", mode="ro")])

        errors = validate_mounts_config(config)

        assert any("Mount target cannot be empty" in e for e in errors)

    def test_volumes_not_a_list_rejected(self):
        config = MountsConfig(volumes="nope")

        errors = validate_mounts_config(config)

        assert errors == ["Mounts volumes must be a list"]


class TestLoadTomlIfExists:
    def test_missing_returns_empty(self, tmp_path):
        assert load_toml_if_exists(tmp_path / "nope.toml") == {}

    def test_existing_parsed(self, tmp_path):
        path = tmp_path / "c.toml"
        path.write_text('[docker]\nimage = "x"\n')

        assert load_toml_if_exists(path) == {"docker": {"image": "x"}}


class TestLoadConfig:
    def test_valid_project(self, project_dir):
        result = load_config(project_dir)

        assert result.docker.image == "iterare-llm:latest"
        assert result.firewall.allowed_domains == ["pypi.org"]

    def test_no_config_files_uses_defaults(self, tmp_path, isolate_global_config):
        # Neither global nor project config exists -> built-in defaults.
        result = load_config(tmp_path)

        assert result.docker.image == DEFAULT_DOCKER_IMAGE
        assert result.firewall.allowed_domains == []
        assert result.mounts.volumes == []

    def test_global_only_provides_defaults(self, tmp_path, isolate_global_config):
        isolate_global_config.parent.mkdir(parents=True, exist_ok=True)
        isolate_global_config.write_text(
            '[docker]\nimage = "global-image"\n'
            "[mounts]\n"
            'volumes = ["~/.gitconfig:/home/node/.gitconfig:ro"]\n'
        )

        result = load_config(tmp_path)

        assert result.docker.image == "global-image"
        assert result.mounts.volumes == [
            Mount(source="~/.gitconfig", target="/home/node/.gitconfig", mode="ro")
        ]

    def test_project_overrides_global(self, project_dir, isolate_global_config):
        isolate_global_config.parent.mkdir(parents=True, exist_ok=True)
        isolate_global_config.write_text(
            '[docker]\nimage = "global-image"\n'
            "[firewall]\n"
            'allowed_domains = ["global.example"]\n'
            "[mounts]\n"
            'volumes = ["~/.gitconfig:/home/node/.gitconfig:ro"]\n'
        )

        result = load_config(project_dir)

        # Project sets image + firewall, so those replace the global values...
        assert result.docker.image == "iterare-llm:latest"
        assert result.firewall.allowed_domains == ["pypi.org"]
        # ...but mounts (absent in the project config) fall through to global.
        assert result.mounts.volumes == [
            Mount(source="~/.gitconfig", target="/home/node/.gitconfig", mode="ro")
        ]

    def test_invalid_values_raises_config_error(self, tmp_path):
        iterare_dir = tmp_path / ".iterare"
        iterare_dir.mkdir()
        shutil.copy(
            TEST_FILES / "invalid_values_config.toml", iterare_dir / "config.toml"
        )

        with pytest.raises(ConfigError, match="Configuration validation failed"):
            load_config(tmp_path)
