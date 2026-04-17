"""Launch an interactive Claude Code session in an isolated Docker container."""

import subprocess
from pathlib import Path
from typing import Optional

import typer

from iterare_llm.commands.common import (
    resolve_environment_variables,
    resolve_project_dir,
    run_id_autocomplete,
    validate_launch_requirements,
)
from iterare_llm.config import (
    load_config,
    get_claude_credentials_path,
    validate_credentials,
)
from iterare_llm.docker import (
    get_docker_client,
    generate_container_name,
    get_image_user,
    generate_domains_file,
)
from iterare_llm.exceptions import (
    IterareError,
    ImageNotFoundError,
    ContainerAlreadyRunningError,
)
from iterare_llm.git import (
    is_git_repository,
    get_current_branch,
    create_worktree,
    get_worktree_path,
    worktree_exists,
)
from iterare_llm.logging import get_logger
from iterare_llm.paths import get_log_file_path
from iterare_llm.run import generate_run_name, register_run

logger = get_logger(__name__)


def build_docker_run_command(
    image_name: str,
    container_name: str,
    worktree_path: Path,
    credentials_path: Path,
    config_file: Path,
    domains_file: Path,
    log_file: Path,
    container_user: str,
    environment: dict[str, str] | None = None,
) -> list[str]:
    """
    Build docker run command for interactive session.

    Parameters
    ----------
    image_name : str
        Docker image name
    container_name : str
        Name for the container
    worktree_path : Path
        Path to the worktree on host
    credentials_path : Path
        Path to credentials directory on host
    config_file : Path
        Path to claude config file on host
    domains_file : Path
        Path to domains file on host
    log_file : Path
        Path to log file on host
    container_user : str
        User the container runs as
    environment : dict[str, str] | None
        Environment variables to pass to the container

    Returns
    -------
    list[str]
        Docker run command as list of arguments
    """
    if container_user == "root":
        home_dir = "/root"
    else:
        home_dir = f"/home/{container_user}"

    credentials_file = credentials_path / ".credentials.json"
    credentials_mount = f"{home_dir}/.claude/.credentials.json"
    config_mount = f"{home_dir}/.claude.json"

    cmd = [
        "docker",
        "run",
        "-it",
        "--rm",
        "--name",
        container_name,
        "--cap-add",
        "NET_ADMIN",
        "-w",
        "/workspace",
        "-e",
        "ITERARE_MODE=interactive",
    ]

    if environment:
        for key, value in environment.items():
            cmd.extend(["-e", f"{key}={value}"])
            logger.debug(f"Added environment variable: {key}")

    cmd.extend(
        [
            "-v",
            f"{worktree_path}:/workspace:rw",
            "-v",
            f"{credentials_file}:{credentials_mount}:rw",
            "-v",
            f"{config_file}:{config_mount}:rw",
            "-v",
            f"{domains_file}:/etc/iterare-domains.txt:ro",
            "-v",
            f"{log_file}:/var/log/iterare.log:rw",
            image_name,
        ]
    )

    return cmd


def interactive(
    workspace: Optional[str] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace name (defaults to generated name)",
    ),
    project_dir: Optional[Path] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project directory (defaults to current directory)",
    ),
    branch: Optional[str] = typer.Option(
        None,
        "--branch",
        "-b",
        help="Branch to base worktree on (defaults to current branch)",
    ),
    reuse: Optional[str] = typer.Option(
        None,
        "--reuse",
        "-r",
        help="Reuse existing workspace from run ID",
        autocompletion=run_id_autocomplete,
    ),
    no_worktree: bool = typer.Option(
        True,
        "--no-worktree/--worktree",
        help="Run directly in project directory without creating a worktree",
    ),
    env: Optional[list[str]] = typer.Option(
        None,
        "--env",
        "-e",
        help="Environment variable to pass through (can be used multiple times)",
    ),
) -> None:
    """
    Launch an interactive Claude Code session in an isolated Docker container.

    By default, runs directly in the project directory. Optionally creates a
    git worktree for isolation when --worktree is specified.

    Examples
    --------
    Start interactive session in current directory (default):
        iterare interactive

    Start with git worktree and auto-generated workspace name:
        iterare interactive --worktree

    Start worktree with specific workspace name:
        iterare interactive --worktree --workspace my-feature

    Start worktree on specific branch:
        iterare interactive --worktree --branch main

    Reuse existing workspace:
        iterare interactive --reuse my-feature-abc12345

    Pass environment variables:
        iterare interactive --env PIP_INDEX_URL --env CUSTOM_VAR
    """
    logger.info("Interactive command invoked")

    worktree_created = False

    try:
        # 1. Resolve project directory
        repo_path = resolve_project_dir(project_dir)

        # 2. Verify this is a git repository
        if not is_git_repository(repo_path):
            error_msg = f"Not a git repository: {repo_path}"
            logger.error(error_msg)
            typer.echo(f"Error: {error_msg}", err=True)
            raise typer.Exit(1)

        # 3. Load configuration and validate credentials
        logger.info("Loading configuration")
        config = load_config(repo_path)
        validate_credentials(config)

        # 4. Get Docker client
        logger.info("Connecting to Docker")
        docker_client = get_docker_client()

        # 5. Determine workspace path and name
        if no_worktree:
            logger.info("Running in project directory (no worktree)")
            if workspace:
                run_name = workspace
            else:
                run_name = generate_run_name("interactive")
            worktree_path = repo_path
            base_branch = "N/A"
        elif reuse:
            logger.info(f"Reusing existing workspace for run: {reuse}")
            run_name = reuse

            worktree_path = get_worktree_path(repo_path, run_name)

            if not worktree_exists(repo_path, run_name):
                error_msg = (
                    f"Worktree for run '{run_name}' does not exist. Cannot reuse."
                )
                logger.error(error_msg)
                typer.echo(f"Error: {error_msg}", err=True)
                raise typer.Exit(1)

            logger.info(f"Found existing worktree at: {worktree_path}")
            base_branch = "N/A"
        else:
            base_name = workspace or "interactive"
            run_name = generate_run_name(base_name)
            base_branch = branch or get_current_branch(repo_path)
            logger.info(f"Generated run name: {run_name}")

        # 6. Validate requirements
        validate_launch_requirements(config, docker_client, run_name)

        # 7. Create git worktree (if needed)
        if not no_worktree and not reuse:
            logger.info(f"Creating worktree for run: {run_name}")
            worktree_path = create_worktree(repo_path, run_name, base_branch)
            worktree_created = True
            logger.info(f"Worktree created at: {worktree_path}")

        # 8. Prepare files for container
        credentials_path = get_claude_credentials_path(config)
        claude_config_file = credentials_path / ".claude.json"

        container_user = get_image_user(docker_client, config.docker.image)
        logger.info(f"Container will run as user: {container_user}")

        domains_file = generate_domains_file(config.firewall.allowed_domains, run_name)
        logger.info(
            f"Generated domains file with {len(config.firewall.allowed_domains)} domains"
        )

        log_file = get_log_file_path(run_name)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.touch()
        log_file.chmod(0o666)
        logger.info(f"Created log file at {log_file}")

        # 9. Resolve environment variables if provided
        environment_vars = None
        if env and isinstance(env, list):
            logger.info(f"Resolving {len(env)} environment variables from host")
            environment_vars = resolve_environment_variables(env)

        # 10. Build docker run command
        container_name = generate_container_name(run_name)
        docker_cmd = build_docker_run_command(
            image_name=config.docker.image,
            container_name=container_name,
            worktree_path=worktree_path,
            credentials_path=credentials_path,
            config_file=claude_config_file,
            domains_file=domains_file,
            log_file=log_file,
            container_user=container_user,
            environment=environment_vars,
        )

        # 11. Register run (if created new worktree)
        if worktree_created:
            register_run(repo_path, run_name, "interactive")

        # 12. Display launch message
        typer.echo(f"\nLaunching interactive session '{run_name}'...")
        typer.echo(f"  Workspace: {worktree_path}")
        if base_branch != "N/A":
            typer.echo(f"  Branch: {base_branch}")
        typer.echo(f"  Container: {container_name}")
        typer.echo("\nStarting Claude Code... (Ctrl+C to exit)\n")

        # 13. Launch interactive container
        logger.info(f"Running: {' '.join(docker_cmd)}")
        result = subprocess.run(docker_cmd)

        # 14. Report exit status
        if result.returncode == 0:
            typer.echo("\n\nInteractive session ended successfully.")
        else:
            typer.echo(f"\n\nSession ended with exit code: {result.returncode}")

        if worktree_created:
            typer.echo(f"\nWorkspace preserved at: {worktree_path}")
            typer.echo(f"To clean up: iterare cleanup {run_name}")

    except KeyboardInterrupt:
        typer.echo("\n\nSession interrupted.", err=True)
        raise typer.Exit(130)

    except ImageNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    except ContainerAlreadyRunningError as e:
        typer.echo(f"Error: {e}", err=True)
        typer.echo(
            "\nTo stop the container, use: docker stop <container-name>",
            err=True,
        )
        raise typer.Exit(1)

    except IterareError as e:
        typer.echo(f"Error: {e}", err=True)
        logger.exception("Interactive session failed")
        raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error during interactive session")
        raise typer.Exit(1)
