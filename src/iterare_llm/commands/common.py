"""Shared utilities for command modules."""

import os
from pathlib import Path
from typing import Optional

import docker
import typer

from iterare_llm.config import Config
from iterare_llm.docker import (
    container_running,
    ensure_image,
    generate_container_name,
)
from iterare_llm.exceptions import (
    ContainerAlreadyRunningError,
    ImageNotFoundError,
)
from iterare_llm.git import remove_worktree
from iterare_llm.logging import get_logger
from iterare_llm.run import list_runs, list_runs_with_workspaces

logger = get_logger(__name__)


def resolve_project_dir(project_dir: Optional[Path]) -> Path:
    """
    Resolve project directory.

    Parameters
    ----------
    project_dir : Path | None
        Project directory provided by user, or None to use current directory

    Returns
    -------
    Path
        Resolved absolute project directory
    """
    if project_dir is None:
        resolved = Path.cwd()
        logger.debug(f"Using current directory as project dir: {resolved}")
    else:
        resolved = project_dir.resolve()
        logger.debug(f"Using provided project dir: {resolved}")
    return resolved


def run_name_autocomplete(incomplete: str) -> list[str]:
    """
    Autocomplete function for run names.

    Returns list of available run names from the project's runs metadata
    that match the incomplete string.

    Parameters
    ----------
    incomplete : str
        Partial run name typed by user

    Returns
    -------
    list[str]
        List of matching run names
    """
    try:
        project_dir = Path.cwd()
        runs = list_runs(project_dir)
        names = [run["run_name"] for run in runs]
        if incomplete:
            names = [n for n in names if n.startswith(incomplete)]
        return names
    except Exception:
        return []


def run_id_autocomplete(incomplete: str) -> list[str]:
    """
    Autocomplete function for run IDs with existing workspaces.

    Returns list of run IDs that still have existing workspaces
    and match the incomplete string.

    Parameters
    ----------
    incomplete : str
        Partial run ID typed by user

    Returns
    -------
    list[str]
        List of matching run IDs with existing workspaces
    """
    try:
        project_dir = Path.cwd()
        runs = list_runs_with_workspaces(project_dir)
        if incomplete:
            runs = [r for r in runs if r.startswith(incomplete)]
        return runs
    except Exception:
        return []


def get_current_run(project_dir: Path) -> Optional[str]:
    """
    Get the most recent run name for a project.

    Parameters
    ----------
    project_dir : Path
        Project directory path

    Returns
    -------
    str | None
        Most recent run name, or None if no runs found
    """
    runs = list_runs(project_dir)
    if not runs:
        return None
    return runs[0]["run_name"]


def resolve_environment_variables(env_names: list[str]) -> dict[str, str]:
    """
    Resolve environment variables from host environment.

    Parameters
    ----------
    env_names : list[str]
        List of environment variable names to resolve

    Returns
    -------
    dict[str, str]
        Dictionary mapping variable names to their values

    Raises
    ------
    typer.Exit
        If any environment variable is not set
    """
    logger.debug(f"Resolving {len(env_names)} environment variables from host")

    env_dict = {}
    missing_vars = []

    for var_name in env_names:
        value = os.environ.get(var_name)
        if value is None:
            missing_vars.append(var_name)
        else:
            env_dict[var_name] = value
            logger.debug(f"Resolved {var_name}={value}")

    if missing_vars:
        error_msg = f"Environment variable(s) not set: {', '.join(missing_vars)}"
        logger.error(error_msg)
        typer.echo(f"Error: {error_msg}", err=True)
        raise typer.Exit(1)

    logger.info(f"Resolved {len(env_dict)} environment variables")
    return env_dict


def cleanup_on_interrupt(repo_path: Path, worktree_name: str) -> None:
    """
    Clean up worktree on interrupt.

    Parameters
    ----------
    repo_path : Path
        Path to git repository
    worktree_name : str
        Name of worktree to remove
    """
    logger.warning(f"Cleaning up worktree: {worktree_name}")
    try:
        remove_worktree(repo_path, worktree_name)
        logger.info(f"Successfully removed worktree: {worktree_name}")
    except Exception as e:
        logger.error(f"Failed to remove worktree during cleanup: {e}")


def validate_launch_requirements(
    config: Config,
    docker_client: docker.DockerClient,
    workspace_name: str,
) -> None:
    """
    Validate pre-flight requirements for container launch.

    Checks that the Docker image exists and no container is already
    running for the given workspace.

    Parameters
    ----------
    config : Config
        Configuration object
    docker_client : docker.DockerClient
        Docker client instance
    workspace_name : str
        Workspace name to check

    Raises
    ------
    ImageNotFoundError
        If Docker image doesn't exist
    ContainerAlreadyRunningError
        If container already running for this workspace
    """
    logger.debug("Validating launch requirements")

    ensure_image(docker_client, config.docker.image)

    container_name = generate_container_name(workspace_name)
    if container_running(docker_client, container_name):
        raise ContainerAlreadyRunningError(
            f"Container already running for workspace '{workspace_name}'. "
            "Stop it first or use a different workspace name."
        )

    logger.debug("Launch requirements validated")
