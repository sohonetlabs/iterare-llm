"""Docker container management for iterare."""

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

import docker
import docker.errors

from iterare_llm.exceptions import (
    ContainerAlreadyRunningError,
    DockerError,
    ImageNotFoundError,
)
from iterare_llm.logging import get_logger
from iterare_llm.paths import get_log_file_path, get_tmp_dir

logger = get_logger(__name__)


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

    # Add environment variables if provided
    if config.environment:
        container_config["environment"] = config.environment
        logger.debug(
            f"Added {len(config.environment)} environment variables to container"
        )

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

    # Check if image exists
    if not image_exists(client, config.image_name):
        raise ImageNotFoundError(
            dedent(f"""
            Docker image '{config.image_name}' not found.
            Please build the image first.
            """).lstrip()
        )

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
