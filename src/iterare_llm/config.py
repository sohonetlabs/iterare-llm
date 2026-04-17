"""Configuration loading and validation for iterare."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from platformdirs import user_config_dir

from iterare_llm.exceptions import ConfigError, CredentialsNotFoundError
from iterare_llm.logging import get_logger

logger = get_logger(__name__)

# Configuration defaults
DEFAULT_DOCKER_IMAGE = "sohonet/iterare-llm:latest"
DEFAULT_SHELL = "/bin/bash"


def get_default_credentials_path() -> str:
    """
    Get the default credentials path using platformdirs.

    Returns
    -------
    str
        Default credentials path

    Examples
    --------
    >>> path = get_default_credentials_path()
    >>> 'iterare' in path
    True
    """
    return user_config_dir("iterare", ensure_exists=False)


DEFAULT_CREDENTIALS_PATH = get_default_credentials_path()


@dataclass
class DockerConfig:
    """Docker configuration settings."""

    image: str


@dataclass
class SessionConfig:
    """Session configuration settings."""

    shell: str


@dataclass
class ClaudeConfig:
    """Claude configuration settings."""

    credentials_path: str


@dataclass
class FirewallConfig:
    """Firewall configuration settings."""

    allowed_domains: list[str]


@dataclass
class Config:
    """Main configuration container."""

    docker: DockerConfig
    session: SessionConfig
    claude: ClaudeConfig
    firewall: FirewallConfig


def expand_path(path_str: str) -> Path:
    """
    Expand ~ and environment variables in a path string.

    Parameters
    ----------
    path_str : str
        Path string that may contain ~ or environment variables

    Returns
    -------
    Path
        Expanded absolute path

    Examples
    --------
    >>> expand_path("~/file.txt")
    Path('/home/user/file.txt')
    >>> expand_path("$HOME/file.txt")
    Path('/home/user/file.txt')
    """
    expanded = os.path.expanduser(os.path.expandvars(path_str))
    return Path(expanded).resolve()


def parse_toml_config(config_path: Path) -> dict:
    """
    Parse TOML configuration file.

    Parameters
    ----------
    config_path : Path
        Path to the TOML configuration file

    Returns
    -------
    dict
        Parsed configuration dictionary

    Raises
    ------
    ConfigError
        If TOML file cannot be parsed
    FileNotFoundError
        If configuration file does not exist
    """
    logger.debug(f"Parsing TOML config from {config_path}")

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        logger.debug("Successfully parsed TOML configuration")
        return data
    except tomllib.TOMLDecodeError as e:
        logger.error(f"Invalid TOML syntax in config file: {e}")
        raise ConfigError(f"Invalid TOML syntax in {config_path}: {e}") from e


def build_config_from_dict(data: dict) -> Config:
    """
    Build Config object from dictionary.

    Parameters
    ----------
    data : dict
        Configuration dictionary from TOML file

    Returns
    -------
    Config
        Constructed configuration object
    """
    docker_section = data.get("docker", dict())
    docker_config = DockerConfig(
        image=docker_section.get("image", DEFAULT_DOCKER_IMAGE)
    )

    session_section = data.get("session", dict())
    session_config = SessionConfig(shell=session_section.get("shell", DEFAULT_SHELL))

    claude_section = data.get("claude", dict())
    claude_config = ClaudeConfig(
        credentials_path=claude_section.get(
            "credentials_path", DEFAULT_CREDENTIALS_PATH
        )
    )

    firewall_section = data.get("firewall", dict())
    firewall_config = FirewallConfig(
        allowed_domains=firewall_section.get("allowed_domains", [])
    )

    logger.debug("Successfully built config from dictionary")
    return Config(
        docker=docker_config,
        session=session_config,
        claude=claude_config,
        firewall=firewall_config,
    )


def validate_docker_config(docker: DockerConfig) -> list[str]:
    """
    Validate Docker configuration.

    Parameters
    ----------
    docker : DockerConfig
        Docker configuration to validate

    Returns
    -------
    list[str]
        List of validation error messages (empty if valid)
    """
    errors = []
    if not docker.image:
        errors.append("Docker image name cannot be empty")
    return errors


def validate_claude_config(claude: ClaudeConfig) -> list[str]:
    """
    Validate Claude configuration.

    Parameters
    ----------
    claude : ClaudeConfig
        Claude configuration to validate

    Returns
    -------
    list[str]
        List of validation error messages (empty if valid)
    """
    errors = []
    if not claude.credentials_path:
        errors.append("Claude credentials path cannot be empty")
    return errors


def validate_firewall_config(firewall: FirewallConfig) -> list[str]:
    """
    Validate firewall configuration.

    Parameters
    ----------
    firewall : FirewallConfig
        Firewall configuration to validate

    Returns
    -------
    list[str]
        List of validation error messages (empty if valid)
    """
    errors = []
    if not isinstance(firewall.allowed_domains, list):
        errors.append("Firewall allowed_domains must be a list")
    else:
        for domain in firewall.allowed_domains:
            if not isinstance(domain, str):
                errors.append(f"Firewall domain must be a string, got: {type(domain)}")
            elif not domain.strip():
                errors.append("Firewall domain cannot be empty or whitespace")
    return errors


def validate_config(config: Config) -> list[str]:
    """
    Validate configuration.

    Parameters
    ----------
    config : Config
        Configuration to validate

    Returns
    -------
    list[str]
        List of validation error messages (empty if valid)
    """
    logger.debug("Validating configuration")
    errors = []

    errors.extend(validate_docker_config(config.docker))
    errors.extend(validate_claude_config(config.claude))
    errors.extend(validate_firewall_config(config.firewall))

    if errors:
        logger.warning(f"Configuration validation failed with {len(errors)} errors")
        for error in errors:
            logger.warning(f"  - {error}")
    else:
        logger.debug("Configuration validation passed")

    return errors


def get_claude_credentials_path(config: Config) -> Path:
    """
    Resolve Claude credentials path from configuration.

    Parameters
    ----------
    config : Config
        Configuration object

    Returns
    -------
    Path
        Resolved absolute path to Claude credentials

    Examples
    --------
    >>> config = load_config(Path("/project"))
    >>> get_claude_credentials_path(config)
    PosixPath('/home/user/.config/iterare')
    """
    path = expand_path(config.claude.credentials_path)
    logger.debug(f"Resolved Claude credentials path: {path}")
    return path


def credentials_exist(path: Path) -> bool:
    """
    Check if Claude credentials exist at the given path.

    Parameters
    ----------
    path : Path
        Path to check for credentials

    Returns
    -------
    bool
        True if credentials directory exists, False otherwise
    """
    exists = path.exists() and path.is_dir()
    logger.debug(
        f"Checking credentials at {path}: {'exists' if exists else 'not found'}"
    )
    return exists


def validate_credentials(config: Config) -> None:
    """
    Validate that Claude credentials exist on disk.

    Parameters
    ----------
    config : Config
        Configuration object

    Raises
    ------
    CredentialsNotFoundError
        If credentials directory does not exist
    """
    credentials_path = get_claude_credentials_path(config)
    if not credentials_exist(credentials_path):
        raise CredentialsNotFoundError(
            dedent(f"""
            Claude credentials not found at {credentials_path}.
            Please ensure Claude Code is configured with valid credentials.
            """).lstrip()
        )


def load_config(project_dir: Path) -> Config:
    """
    Load configuration from .iterare/config.toml.

    Parameters
    ----------
    project_dir : Path
        Project directory containing .iterare/

    Returns
    -------
    Config
        Loaded and validated configuration

    Raises
    ------
    ConfigError
        If configuration is invalid or credentials not found
    FileNotFoundError
        If configuration file doesn't exist
    """
    config_path = project_dir / ".iterare" / "config.toml"
    logger.debug(f"Loading configuration from {config_path}")

    data = parse_toml_config(config_path)
    config = build_config_from_dict(data)

    # Validate configuration
    validation_errors = validate_config(config)
    if validation_errors:
        error_list = "\n".join(f"  - {err}" for err in validation_errors)
        error_msg = f"Configuration validation failed:\n{error_list}"
        raise ConfigError(error_msg)

    logger.info(f"Successfully loaded configuration from {config_path}")
    return config
