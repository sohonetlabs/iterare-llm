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

# Valid Docker bind-mount access modes (compose short syntax).
VALID_MOUNT_MODES = ("ro", "rw")

GLOBAL_CONFIG_TEMPLATE = dedent(f"""
    # iterare global configuration
    #
    # These settings apply to every iterare project unless overridden by a
    # project-level .iterare/config.toml. Every value below is commented out,
    # which means the built-in default shown is used. Uncomment and edit a value
    # to change the default behaviour for all projects.

    [docker]
    # Docker image used to run Claude Code.
    # image = "{DEFAULT_DOCKER_IMAGE}"

    [session]
    # Shell used for interactive sessions.
    # shell = "{DEFAULT_SHELL}"

    [claude]
    # Directory containing Claude credentials
    # (.credentials.json and .claude.json).
    # credentials_path = "{DEFAULT_CREDENTIALS_PATH}"

    [firewall]
    # Additional domains to allow through the firewall. Default domains
    # (npm, anthropic, github, etc.) are always included.
    # allowed_domains = [
    #     "pypi.org",
    #     "files.pythonhosted.org",
    # ]

    [mounts]
    # Extra host paths to bind-mount into every container, using Docker-compose
    # short syntax: "SOURCE:TARGET[:MODE]". SOURCE supports ~ and $VAR expansion;
    # MODE defaults to "rw" and may be "ro" or "rw".
    # volumes = [
    #     "~/.gitconfig:/home/node/.gitconfig:ro",
    #     "~/.aws:/home/node/.aws:ro",
    # ]
    """).lstrip()


def get_global_config_path() -> Path:
    """
    Get the path to the global iterare configuration file.

    The global config holds machine-wide defaults that every project inherits
    unless overridden by a project-level `.iterare/config.toml`. It lives at
    `~/.iterare/config.toml` (note: distinct from the platformdirs credentials
    directory).

    Returns
    -------
    Path
        Path to the global configuration file
    """
    return Path.home() / ".iterare" / "config.toml"


def create_global_config() -> bool:
    """
    Create the global iterare config file if it does not already exist.

    The global config holds machine-wide defaults (see
    :func:`get_global_config_path`). An existing file is never overwritten, so
    user edits are preserved across repeated `init`/`install` runs. This is
    shared by both the `init` and `install` commands.

    Returns
    -------
    bool
        True if the file was created, False if it already existed
    """
    global_path = get_global_config_path()
    if global_path.exists():
        logger.debug(f"Global config already exists at {global_path}, leaving as-is")
        return False

    logger.debug(f"Creating global config directory: {global_path.parent}")
    global_path.parent.mkdir(parents=True, exist_ok=True)

    logger.debug(f"Writing global config: {global_path}")
    global_path.write_text(GLOBAL_CONFIG_TEMPLATE)
    return True


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
class Mount:
    """
    A single host-to-container bind mount.

    Attributes
    ----------
    source : str
        Host path to mount. May contain `~` or environment variables; it is
        expanded when the mount is built, not when parsed.
    target : str
        Absolute path inside the container to mount onto.
    mode : str
        Access mode, one of `ro` or `rw`. Defaults to `rw`.
    """

    source: str
    target: str
    mode: str = "rw"


@dataclass
class MountsConfig:
    """Extra bind mounts applied to every container."""

    volumes: list[Mount]


@dataclass
class Config:
    """Main configuration container."""

    docker: DockerConfig
    session: SessionConfig
    claude: ClaudeConfig
    firewall: FirewallConfig
    mounts: MountsConfig


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


def parse_mount_spec(spec: str) -> Mount:
    """
    Parse a Docker-compose short-syntax bind-mount specification.

    The expected format is `"SOURCE:TARGET[:MODE]"` where `MODE` is one of
    `ro` or `rw` (defaulting to `rw`). `SOURCE` may contain `~` or
    environment variables; expansion is deferred until the mount is built.

    Parameters
    ----------
    spec : str
        Mount specification string

    Returns
    -------
    Mount
        Parsed mount

    Raises
    ------
    ConfigError
        If the specification is malformed (e.g. missing a target)

    Examples
    --------
    >>> parse_mount_spec("~/.gitconfig:/home/node/.gitconfig:ro")
    Mount(source='~/.gitconfig', target='/home/node/.gitconfig', mode='ro')
    >>> parse_mount_spec("/data:/workspace/data")
    Mount(source='/data', target='/workspace/data', mode='rw')
    """
    if not isinstance(spec, str):
        raise ConfigError(f"Mount specification must be a string, got: {type(spec)}")

    parts = spec.split(":")

    # An optional trailing mode is only consumed when it is a recognised mode;
    # this keeps unix sources (which never contain a bare "ro"/"rw" segment)
    # unambiguous without special-casing.
    mode = "rw"
    if len(parts) >= 3 and parts[-1] in VALID_MOUNT_MODES:
        mode = parts[-1]
        parts = parts[:-1]

    if len(parts) < 2:
        raise ConfigError(
            f"Invalid mount specification '{spec}'. Expected \"SOURCE:TARGET[:MODE]\"."
        )

    target = parts[-1]
    # Rejoin any leading segments as the source to tolerate stray colons.
    source = ":".join(parts[:-1])

    if not source.strip():
        raise ConfigError(f"Mount specification '{spec}' has an empty source")
    if not target.strip():
        raise ConfigError(f"Mount specification '{spec}' has an empty target")

    return Mount(source=source, target=target, mode=mode)


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


def load_toml_if_exists(config_path: Path) -> dict:
    """
    Parse a TOML config file, returning an empty dict if it does not exist.

    Unlike :func:`parse_toml_config`, a missing file is not an error. This is
    used for the layered config load where both the global and project files are
    optional.

    Parameters
    ----------
    config_path : Path
        Path to the TOML configuration file

    Returns
    -------
    dict
        Parsed configuration dictionary, or an empty dict if the file is absent

    Raises
    ------
    ConfigError
        If the file exists but contains invalid TOML
    """
    if not config_path.exists():
        logger.debug(f"Config file not found (skipping): {config_path}")
        return dict()
    return parse_toml_config(config_path)


def merge_config_dicts(base: dict, override: dict) -> dict:
    """
    Overlay one config dict on top of another at the table-key level.

    For each top-level section (table), keys present in `override` replace the
    corresponding keys in `base`. List values are replaced wholesale, not
    concatenated. Sections present in only one of the inputs are kept as-is.

    Parameters
    ----------
    base : dict
        Lower-precedence configuration (e.g. the global config)
    override : dict
        Higher-precedence configuration (e.g. the project config)

    Returns
    -------
    dict
        Merged configuration dictionary

    Examples
    --------
    >>> merge_config_dicts(
    ...     {"docker": {"image": "a"}, "firewall": {"allowed_domains": ["x"]}},
    ...     {"firewall": {"allowed_domains": ["y"]}},
    ... )
    {'docker': {'image': 'a'}, 'firewall': {'allowed_domains': ['y']}}
    """
    merged: dict = dict()
    for section in set(base) | set(override):
        base_table = base.get(section, dict())
        override_table = override.get(section, dict())
        if isinstance(base_table, dict) and isinstance(override_table, dict):
            merged[section] = {**base_table, **override_table}
        else:
            # Non-table values (unexpected at top level) follow override-wins.
            merged[section] = override.get(section, base.get(section))
    return merged


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

    mounts_section = data.get("mounts", dict())
    mount_specs = mounts_section.get("volumes", [])
    if not isinstance(mount_specs, list):
        raise ConfigError(f"Mounts volumes must be a list, got: {type(mount_specs)}")
    mounts_config = MountsConfig(
        volumes=[parse_mount_spec(spec) for spec in mount_specs]
    )

    logger.debug("Successfully built config from dictionary")
    return Config(
        docker=docker_config,
        session=session_config,
        claude=claude_config,
        firewall=firewall_config,
        mounts=mounts_config,
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


def validate_mounts_config(mounts: MountsConfig) -> list[str]:
    """
    Validate mounts configuration.

    Parameters
    ----------
    mounts : MountsConfig
        Mounts configuration to validate

    Returns
    -------
    list[str]
        List of validation error messages (empty if valid)
    """
    errors = []
    for mount in mounts.volumes:
        if not mount.source.strip():
            errors.append("Mount source cannot be empty")
        if not mount.target.strip():
            errors.append("Mount target cannot be empty")
        elif not mount.target.startswith("/"):
            errors.append(
                f"Mount target must be an absolute path, got: '{mount.target}'"
            )

        if mount.mode not in VALID_MOUNT_MODES:
            errors.append(
                f"Mount mode must be one of {VALID_MOUNT_MODES}, got: '{mount.mode}'"
            )
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
    errors.extend(validate_mounts_config(config.mounts))

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
    Load configuration, merging the global and project config layers.

    Settings are resolved in three layers of increasing precedence:

    1. Built-in defaults
    2. Global config at `~/.iterare/config.toml`
    3. Project config at `<project_dir>/.iterare/config.toml`

    A key present in a higher layer fully overrides the same key in a lower
    layer (lists are replaced, not merged). Both files are optional; if neither
    exists, built-in defaults are used.

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
    """
    global_path = get_global_config_path()
    project_path = project_dir / ".iterare" / "config.toml"
    logger.debug(
        f"Loading configuration (global: {global_path}, project: {project_path})"
    )

    global_data = load_toml_if_exists(global_path)
    project_data = load_toml_if_exists(project_path)
    logger.debug(
        f"Config layers found - global: {bool(global_data)}, "
        f"project: {bool(project_data)}"
    )

    merged_data = merge_config_dicts(global_data, project_data)
    config = build_config_from_dict(merged_data)

    # Validate configuration
    validation_errors = validate_config(config)
    if validation_errors:
        error_list = "\n".join(f"  - {err}" for err in validation_errors)
        error_msg = f"Configuration validation failed:\n{error_list}"
        raise ConfigError(error_msg)

    logger.info("Successfully loaded configuration")
    return config
