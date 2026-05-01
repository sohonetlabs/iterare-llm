"""Docker container management for iterare."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent

import docker
import docker.errors
import yaml

from iterare_llm.exceptions import (
    ContainerAlreadyRunningError,
    DockerError,
    ImageNotFoundError,
    NetworkNotFoundError,
)
from iterare_llm.logging import get_logger
from iterare_llm.paths import get_log_file_path, get_tmp_dir

logger = get_logger(__name__)

NETWORK_SUBNETS_ENV_VAR = "ITERARE_NETWORK_SUBNETS"


@dataclass
class ExecutionConfig:
    """Configuration for container execution."""

    image_name: str
    worktree_path: Path
    workspace_name: str
    claude_credentials_path: Path
    claude_config_file: Path
    prompt_content: str
    allowed_domains: list[str]
    environment: dict[str, str] | None = None
    networks: list[str] = field(default_factory=list)
    network_subnets: list[str] = field(default_factory=list)


def get_docker_client() -> docker.DockerClient:
    """
    Get a Docker client with error handling.

    Returns
    -------
    docker.DockerClient
        Connected Docker client

    Raises
    ------
    DockerError
        If unable to connect to Docker daemon
    """
    logger.debug("Connecting to Docker daemon")

    try:
        client = docker.from_env()
        # Test connection
        client.ping()
        logger.debug("Successfully connected to Docker daemon")
        return client
    except docker.errors.DockerException as e:
        logger.error(f"Failed to connect to Docker daemon: {e}")
        raise DockerError(
            dedent(f"""
            Failed to connect to Docker daemon: {e}
            Is Docker running?
            """).lstrip()
        ) from e


def image_exists(client: docker.DockerClient, image_name: str) -> bool:
    """
    Check if a Docker image exists locally.

    Parameters
    ----------
    client : docker.DockerClient
        Docker client
    image_name : str
        Name of the image to check (e.g., "image:tag")

    Returns
    -------
    bool
        True if image exists, False otherwise

    Examples
    --------
    >>> client = get_docker_client()
    >>> image_exists(client, "ubuntu:latest")
    True
    """
    logger.debug(f"Checking if image exists: {image_name}")

    try:
        client.images.get(image_name)
        logger.debug(f"Image found: {image_name}")
        return True
    except docker.errors.ImageNotFound:
        logger.debug(f"Image not found: {image_name}")
        return False
    except docker.errors.DockerException as e:
        logger.error(f"Error checking image existence: {e}")
        raise DockerError(f"Error checking image existence: {e}") from e


def ensure_image(client: docker.DockerClient, image_name: str) -> None:
    """
    Ensure a Docker image is available locally, pulling from registry if needed.

    Parameters
    ----------
    client : docker.DockerClient
        Docker client
    image_name : str
        Name of the image (e.g., "sohonet/iterare-llm:latest")

    Raises
    ------
    ImageNotFoundError
        If image cannot be found locally or pulled from registry
    DockerError
        If a Docker API error occurs during pull
    """
    if image_exists(client, image_name):
        return

    logger.info(f"Image '{image_name}' not found locally, pulling from registry...")
    try:
        client.images.pull(image_name)
        logger.info(f"Successfully pulled image: {image_name}")
    except docker.errors.ImageNotFound:
        raise ImageNotFoundError(
            f"Image '{image_name}' not found locally or in registry."
        ) from None
    except docker.errors.APIError as e:
        raise DockerError(f"Failed to pull image '{image_name}': {e}") from e


def get_image_user(client: docker.DockerClient, image_name: str) -> str:
    """
    Get the user that the Docker image runs as.

    Parameters
    ----------
    client : docker.DockerClient
        Docker client
    image_name : str
        Name of the image to inspect

    Returns
    -------
    str
        Username or UID that the image runs as. Returns "root" if not specified.

    Raises
    ------
    ImageNotFoundError
        If image doesn't exist
    DockerError
        If unable to inspect image

    Examples
    --------
    >>> client = get_docker_client()
    >>> get_image_user(client, "node:20-slim")
    'node'
    >>> get_image_user(client, "ubuntu:latest")
    'root'
    """
    logger.debug(f"Getting user for image: {image_name}")

    try:
        image = client.images.get(image_name)
        config = image.attrs.get("Config", {})
        user = config.get("User", "")

        # If User is empty or not set, default to root
        if not user:
            user = "root"
            logger.debug(f"No user specified in image, defaulting to: {user}")
        else:
            logger.debug(f"Image user: {user}")

        return user
    except docker.errors.ImageNotFound:
        logger.error(f"Image not found: {image_name}")
        raise ImageNotFoundError(f"Image '{image_name}' not found") from None
    except docker.errors.DockerException as e:
        logger.error(f"Error inspecting image: {e}")
        raise DockerError(f"Error inspecting image: {e}") from e


def find_container_by_name(
    client: docker.DockerClient, name: str
) -> docker.models.containers.Container | None:
    """
    Find a container by name.

    Parameters
    ----------
    client : docker.DockerClient
        Docker client
    name : str
        Container name to search for

    Returns
    -------
    docker.models.containers.Container | None
        Container object if found, None otherwise
    """
    try:
        containers = client.containers.list(all=True, filters={"name": name})
        for container in containers:
            # Exact match on name (Docker returns containers with names that contain the search term)
            if container.name == name:
                logger.debug(f"Found container: {name}")
                return container
        logger.debug(f"Container not found: {name}")
        return None
    except docker.errors.DockerException as e:
        logger.error(f"Error searching for container: {e}")
        raise DockerError(f"Error searching for container: {e}") from e


def container_running(client: docker.DockerClient, container_name: str) -> bool:
    """
    Check if a container is currently running.

    Parameters
    ----------
    client : docker.DockerClient
        Docker client
    container_name : str
        Name of the container to check

    Returns
    -------
    bool
        True if container exists and is running, False otherwise

    Examples
    --------
    >>> client = get_docker_client()
    >>> container_running(client, "it-task-1")
    False
    """
    logger.debug(f"Checking if container is running: {container_name}")

    container = find_container_by_name(client, container_name)
    if container is None:
        return False

    is_running = container.status == "running"
    logger.debug(
        f"Container {container_name} status: {container.status} (running: {is_running})"
    )
    return is_running


def generate_container_name(workspace: str) -> str:
    """
    Generate a unique container name for a workspace.

    Uses "it" prefix (short for iterare) to keep container names concise.

    Parameters
    ----------
    workspace : str
        Workspace name (typically the run name)

    Returns
    -------
    str
        Container name

    Examples
    --------
    >>> generate_container_name("refactor-api-abc123")
    'it-refactor-api-abc123'
    """
    container_name = f"it-{workspace}"
    logger.debug(f"Generated container name: {container_name}")
    return container_name


def generate_domains_file(allowed_domains: list[str], run_name: str) -> Path:
    """
    Generate a file containing allowed domains in the application tmp directory.

    The file contains one domain per line and will be mounted into the container
    as a root-owned file that the container user cannot modify.

    Each run gets its own domains file to support multiple concurrent runs.

    Parameters
    ----------
    allowed_domains : list[str]
        List of domain names to allow through the firewall
    run_name : str
        Unique run name to namespace the domains file

    Returns
    -------
    Path
        Path to the generated domains file

    Raises
    ------
    OSError
        If unable to write the domains file

    Examples
    --------
    >>> domains = ["example.com", "api.example.org"]
    >>> domains_file = generate_domains_file(domains, "refactor-api-abc123")
    >>> domains_file.read_text()
    'example.com\\napi.example.org\\n'
    >>> "domains-refactor-api-abc123.txt" in str(domains_file)
    True
    """
    logger.debug(
        f"Generating domains file for run '{run_name}' with {len(allowed_domains)} domains"
    )

    try:
        # Get application tmp directory
        tmp_dir = get_tmp_dir()
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # Create domains file with run-specific name
        domains_file = tmp_dir / f"domains-{run_name}.txt"

        # Write domains, one per line
        content = "\n".join(allowed_domains) + "\n" if allowed_domains else ""
        domains_file.write_text(content)

        logger.debug(f"Generated domains file at {domains_file}")
        return domains_file
    except OSError as e:
        logger.error(f"Failed to generate domains file: {e}")
        raise OSError(f"Failed to generate domains file: {e}") from e


def network_exists(client: docker.DockerClient, network_name: str) -> bool:
    """
    Check whether a Docker network exists.

    Parameters
    ----------
    client : docker.DockerClient
        Docker client
    network_name : str
        Network name to look up

    Returns
    -------
    bool
        True if network exists, False otherwise

    Raises
    ------
    DockerError
        If a non-NotFound Docker error occurs while looking up the network
    """
    logger.debug(f"Checking if Docker network exists: {network_name}")
    try:
        client.networks.get(network_name)
        return True
    except docker.errors.NotFound:
        return False
    except docker.errors.DockerException as e:
        logger.error(f"Error inspecting docker network '{network_name}': {e}")
        raise DockerError(f"Error inspecting docker network: {e}") from e


def get_network_subnets(client: docker.DockerClient, network_name: str) -> list[str]:
    """
    Return the IPAM-configured subnets for a Docker network.

    Parameters
    ----------
    client : docker.DockerClient
        Docker client
    network_name : str
        Network name

    Returns
    -------
    list[str]
        List of subnet CIDR strings (e.g. ["172.18.0.0/16"]). Empty if the
        network has no IPAM configuration.

    Raises
    ------
    NetworkNotFoundError
        If the network does not exist
    DockerError
        If a Docker API error occurs
    """
    logger.debug(f"Getting subnets for network '{network_name}'")
    try:
        network = client.networks.get(network_name)
    except docker.errors.NotFound:
        raise NetworkNotFoundError(
            f"Docker network '{network_name}' not found"
        ) from None
    except docker.errors.DockerException as e:
        raise DockerError(f"Error inspecting docker network: {e}") from e

    ipam = network.attrs.get("IPAM") or {}
    configs = ipam.get("Config") or []
    subnets = [c["Subnet"] for c in configs if c.get("Subnet")]
    logger.debug(f"Network '{network_name}' subnets: {subnets}")
    return subnets


def list_docker_networks() -> list[str]:
    """
    List names of Docker networks visible to the current daemon.

    Returns an empty list when Docker is unreachable so this can be used in
    autocomplete callbacks without crashing the shell.

    Returns
    -------
    list[str]
        Names of Docker networks. Empty if Docker is unavailable.
    """
    try:
        client = get_docker_client()
        return [n.name for n in client.networks.list()]
    except Exception:
        return []


def docker_network_autocomplete(incomplete: str) -> list[str]:
    """
    Autocomplete callback for Docker network names.

    Parameters
    ----------
    incomplete : str
        Partial network name typed by the user

    Returns
    -------
    list[str]
        Matching network names
    """
    networks = list_docker_networks()
    if incomplete:
        networks = [n for n in networks if n.startswith(incomplete)]
    return networks


def sanitize_compose_project_name(raw: str) -> str:
    """Apply Docker Compose's project-name normalisation rules."""
    cleaned = re.sub(r"[^a-z0-9_-]+", "", raw.lower())
    return cleaned.lstrip("_-")


def load_compose_file(compose_file: Path) -> dict:
    """Parse a compose file as a dict, returning ``{}`` on read or parse failure."""
    try:
        data = yaml.safe_load(compose_file.read_text())
    except (OSError, yaml.YAMLError) as e:
        logger.debug(f"Could not read compose file '{compose_file}': {e}")
        data = None
    return data if isinstance(data, dict) else {}


def read_compose_project_name(compose_file: Path) -> str | None:
    """Read the optional top-level ``name`` field from a compose file."""
    name = load_compose_file(compose_file).get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    return sanitize_compose_project_name(name)


def detect_compose_network(project_dir: Path) -> str | None:
    """
    Detect the default network name a docker-compose.yml in *project_dir* would create.

    Looks for ``docker-compose.yml`` or ``compose.yml`` in *project_dir*. If
    found, the returned name follows Docker Compose conventions:
    ``<project>_default`` where ``project`` is taken from the compose file's
    top-level ``name:`` field, falling back to a sanitized form of the
    directory name.

    Parameters
    ----------
    project_dir : Path
        Project root to inspect

    Returns
    -------
    str | None
        Network name, or None if no compose file is present
    """
    candidates = [
        project_dir / "docker-compose.yml",
        project_dir / "docker-compose.yaml",
        project_dir / "compose.yml",
        project_dir / "compose.yaml",
    ]
    compose_file = next((c for c in candidates if c.is_file()), None)
    if not compose_file:
        return None

    project_name = read_compose_project_name(compose_file)
    if not project_name:
        # Project name fallback
        if not (project_name := sanitize_compose_project_name(project_dir.name)):
            logger.debug(
                f"Could not derive a compose project name from '{project_dir}'"
            )
            return None

    network_name = f"{project_name}_default"
    logger.debug(f"Detected compose default network: {network_name}")
    return network_name


def get_docker_networks(
    client: docker.DockerClient,
    networks: list[str] | None,
    use_compose: bool,
    project_dir: Path,
) -> list[str]:
    """
    Resolve the list of Docker networks to attach a container to.

    Explicit *networks* are validated and every name must exist or
    :class:`NetworkNotFoundError` is raised. When *use_compose* is true,
    the project directory is additionally scanned for a docker-compose
    file and its default network appended if currently active.

    Parameters
    ----------
    client : docker.DockerClient
        Docker client
    networks : list[str] | None
        Explicit networks requested by the user via ``--docker-network``
    use_compose : bool
        Whether to detect and attach the docker-compose default network
    project_dir : Path
        Project root used to detect docker-compose default networks

    Returns
    -------
    list[str]
        Validated network names, deduplicated. Explicit names appear in
        sorted order; the compose-detected network (if any) is appended
        last.

    Raises
    ------
    NetworkNotFoundError
        If a user-specified network does not exist
    """
    resolved: list[str] = []

    if networks:
        for name in sorted(set(networks)):
            if not network_exists(client, name):
                raise NetworkNotFoundError(f"Docker network '{name}' does not exist.")
            resolved.append(name)

    if use_compose:
        compose_network = detect_compose_network(project_dir)
        if compose_network is None:
            logger.info(
                "No docker-compose file detected in project directory; "
                "skipping compose network attachment."
            )
        elif not network_exists(client, compose_network):
            logger.info(
                f"Detected compose network '{compose_network}' is not currently active; "
                "skipping compose network attachment."
            )
        elif compose_network not in resolved:
            resolved.append(compose_network)

    if resolved:
        logger.info(f"Resolved Docker networks: {resolved}")

    return resolved


def get_docker_network_subnets(
    client: docker.DockerClient, networks: list[str]
) -> list[str]:
    """
    Aggregate the subnets configured for a list of Docker networks.

    Parameters
    ----------
    client : docker.DockerClient
        Docker client
    networks : list[str]
        Network names to inspect

    Returns
    -------
    list[str]
        Deduplicated list of subnet CIDR strings
    """
    subnets = {
        subnet
        for network in networks
        for subnet in get_network_subnets(client, network)
    }
    return sorted(subnets)


def attach_additional_networks(
    client: docker.DockerClient,
    container,
    networks: list[str],
) -> None:
    """
    Connect a running container to extra Docker networks.

    The first attached network is wired up at container creation time
    via Docker SDK's ``network`` parameter, so this helper handles the
    second and subsequent entries by calling ``network.connect``.

    Parameters
    ----------
    client : docker.DockerClient
        Docker client
    container : docker.models.containers.Container
        The running container
    networks : list[str]
        All resolved networks (the first is assumed already attached)

    Raises
    ------
    DockerError
        If the SDK fails to connect a network
    """
    if len(networks) <= 1:
        return

    for name in networks[1:]:
        logger.info(f"Connecting container to additional network '{name}'")
        try:
            client.networks.get(name).connect(container)
        except docker.errors.DockerException as e:
            raise DockerError(
                f"Failed to connect container to network '{name}': {e}"
            ) from e


def build_volume_mounts(
    config: ExecutionConfig, container_user: str, domains_file: Path, log_file: Path
) -> dict:
    """
    Build volume mount configuration for Docker container.

    Mounts only the essential credential files from ~/.iterare/,
    the firewall domains configuration file, and the log file.

    Parameters
    ----------
    config : ExecutionConfig
        Execution configuration
    container_user : str
        User that the container runs as (from get_image_user)
    domains_file : Path
        Path to the generated domains file on the host
    log_file : Path
        Path to the log file on the host

    Returns
    -------
    dict
        Volume mount configuration for Docker SDK
    """
    # Determine the home directory based on the user
    if container_user == "root":
        home_dir = "/root"
    else:
        home_dir = f"/home/{container_user}"

    # Mount paths in container
    credentials_file_mount = f"{home_dir}/.claude/.credentials.json"
    config_file_mount = f"{home_dir}/.claude.json"

    # Source credential files from ~/.iterare/
    credentials_file = config.claude_credentials_path / ".credentials.json"
    config_file = config.claude_config_file

    volumes = {
        str(config.worktree_path): {"bind": "/workspace", "mode": "rw"},
        # Mount credentials file as read-write
        str(credentials_file): {"bind": credentials_file_mount, "mode": "rw"},
        # Mount config file as read-write (Claude updates session info)
        str(config_file): {"bind": config_file_mount, "mode": "rw"},
        # Mount domains file as read-only, owned by root
        str(domains_file): {"bind": "/etc/iterare-domains.txt", "mode": "ro"},
        # Mount log file as read-write for capturing execution logs
        str(log_file): {"bind": "/var/log/iterare.log", "mode": "rw"},
    }

    logger.debug(f"Built volume mounts for user '{container_user}': {volumes}")
    return volumes


def build_container_config(
    config: ExecutionConfig, container_user: str, domains_file: Path, log_file: Path
) -> dict:
    """
    Build full container configuration.

    Parameters
    ----------
    config : ExecutionConfig
        Execution configuration
    container_user : str
        User that the container runs as (from get_image_user)
    domains_file : Path
        Path to the generated domains file on the host
    log_file : Path
        Path to the log file on the host

    Returns
    -------
    dict
        Container configuration for Docker SDK
    """
    container_config = {
        "image": config.image_name,
        "name": generate_container_name(config.workspace_name),
        "volumes": build_volume_mounts(config, container_user, domains_file, log_file),
        "detach": True,
        "auto_remove": True,
        "working_dir": "/workspace",
        "cap_add": ["NET_ADMIN"],
    }

    environment: dict[str, str] = {}
    if config.environment:
        environment.update(config.environment)
        logger.debug(
            f"Added {len(config.environment)} environment variables to container"
        )

    if config.network_subnets:
        environment[NETWORK_SUBNETS_ENV_VAR] = ",".join(config.network_subnets)
        logger.debug(
            f"Passing {len(config.network_subnets)} network subnets to container"
        )

    if environment:
        container_config["environment"] = environment

    if config.networks:
        container_config["network"] = config.networks[0]
        logger.debug(f"Container will start attached to network '{config.networks[0]}'")

    logger.debug(f"Built container config for {config.workspace_name}")
    return container_config


def launch_container(
    client: docker.DockerClient, config: ExecutionConfig, run_name: str
) -> str:
    """
    Launch a Docker container for Claude Code execution.

    Parameters
    ----------
    client : docker.DockerClient
        Docker client
    config : ExecutionConfig
        Execution configuration
    run_name : str
        Unique run name for this execution

    Returns
    -------
    str
        Container ID

    Raises
    ------
    ImageNotFoundError
        If Docker image doesn't exist
    ContainerAlreadyRunningError
        If container with same name is already running
    DockerError
        If unable to launch container

    Examples
    --------
    >>> client = get_docker_client()
    >>> config = ExecutionConfig(
    ...     image_name="claude-code:latest",
    ...     worktree_path=Path("/workspace"),
    ...     workspace_name="task-1",
    ...     claude_credentials_path=Path("~/.claude"),
    ...     prompt_content="Do task"
    ... )
    >>> container_id = launch_container(client, config, "task-1-abc123")
    """
    logger.info(f"Launching container for workspace '{config.workspace_name}'")

    ensure_image(client, config.image_name)

    # Check if container already running
    container_name = generate_container_name(config.workspace_name)
    if container_running(client, container_name):
        raise ContainerAlreadyRunningError(
            dedent(f"""
            Container '{container_name}' is already running.
            Stop it first or use a different workspace name.
            """).lstrip()
        )

    # Determine which user the container runs as
    container_user = get_image_user(client, config.image_name)
    logger.info(f"Container will run as user: {container_user}")

    # Generate domains file for firewall configuration with run-specific name
    domains_file = generate_domains_file(config.allowed_domains, run_name)
    logger.info(f"Generated domains file with {len(config.allowed_domains)} domains")

    # Create log file for this run
    log_file = get_log_file_path(run_name)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.touch()  # Create empty log file
    log_file.chmod(0o666)  # Make world-writable for container access
    logger.info(f"Created log file at {log_file}")

    # Build container configuration
    container_config = build_container_config(
        config, container_user, domains_file, log_file
    )

    # Launch container
    try:
        logger.info(
            f"Starting container '{container_name}' with image '{config.image_name}'"
        )
        container = client.containers.run(**container_config)
        container_id = container.id
        logger.info(f"Successfully launched container: {container_id}")
        attach_additional_networks(client, container, config.networks)
        return container_id
    except docker.errors.ContainerError as e:
        logger.error(f"Container execution failed: {e}")
        raise DockerError(f"Container execution failed: {e}") from e
    except docker.errors.ImageNotFound as e:
        logger.error(f"Image not found: {e}")
        raise ImageNotFoundError(f"Image '{config.image_name}' not found") from e
    except docker.errors.APIError as e:
        logger.error(f"Docker API error: {e}")
        raise DockerError(f"Docker API error: {e}") from e
    except docker.errors.DockerException as e:
        logger.error(f"Docker error: {e}")
        raise DockerError(f"Failed to launch container: {e}") from e
