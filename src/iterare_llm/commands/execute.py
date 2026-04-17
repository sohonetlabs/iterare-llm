"""Execute a prompt in an isolated Docker container."""

from pathlib import Path
from typing import Optional

import typer

from iterare_llm.commands.common import (
    cleanup_on_interrupt,
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
    launch_container,
    ExecutionConfig,
)
from iterare_llm.exceptions import (
    IterareError,
    ImageNotFoundError,
    ContainerAlreadyRunningError,
    CredentialsNotFoundError,
)
from iterare_llm.git import (
    is_git_repository,
    get_current_branch,
    create_worktree,
    get_worktree_path,
    worktree_exists,
)
from iterare_llm.logging import get_logger
from iterare_llm.prompt import (
    resolve_prompt_path,
    parse_prompt_file,
    get_workspace_name_from_prompt,
    list_prompts,
    Prompt,
)
from iterare_llm.run import generate_run_name, register_run
from iterare_llm.workspace import prepare_workspace

logger = get_logger(__name__)


def display_success_message(
    run_name: str,
    container_id: str,
    worktree_path: Path,
    branch: str,
) -> None:
    """
    Display success message after container launch.

    Parameters
    ----------
    run_name : str
        Unique run name
    container_id : str
        Docker container ID
    worktree_path : Path
        Path to worktree
    branch : str
        Branch name used
    """
    container_name = generate_container_name(run_name)

    typer.echo(f"\nLaunching execution for '{run_name}'...")
    typer.echo(f"  Workspace: {worktree_path}")
    typer.echo(f"  Branch: {branch}")
    typer.echo(f"  Container: {container_name}")
    typer.echo("\nContainer launched successfully!")
    typer.echo(f"Container ID: {container_id}")
    typer.echo(f"\nMonitor logs with: iterare log -f {run_name}")


def prompt_name_autocomplete(incomplete: str) -> list[str]:
    """
    Autocomplete function for prompt names.

    Returns list of available prompt names from .iterare/prompts/
    directory that match the incomplete string.

    Parameters
    ----------
    incomplete : str
        Partial prompt name typed by user

    Returns
    -------
    list[str]
        List of matching prompt names (without .md extension)
    """
    try:
        project_dir = Path.cwd()
        prompts = list_prompts(project_dir)
        names = [p.stem for p in prompts]
        if incomplete:
            names = [n for n in names if n.startswith(incomplete)]
        return names
    except Exception:
        return []


def execute(
    prompt_input: str = typer.Argument(
        ..., help="Prompt file name or path", autocompletion=prompt_name_autocomplete
    ),
    project_dir: Optional[Path] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project directory (defaults to current directory)",
    ),
    reuse: Optional[str] = typer.Option(
        None,
        "--reuse",
        "-r",
        help="Reuse existing workspace from run ID",
        autocompletion=run_id_autocomplete,
    ),
    env: Optional[list[str]] = typer.Option(
        None,
        "--env",
        "-e",
        help="Environment variable to pass through (can be used multiple times)",
    ),
) -> None:
    """
    Execute a prompt in an isolated Docker container.

    Creates a git worktree, mounts it in a Docker container,
    and launches Claude Code in dangerous mode to autonomously
    execute the prompt.

    Examples
    --------
    Execute by prompt name:
        iterare execute refactor-api

    Execute by path:
        iterare execute .iterare/prompts/task.md

    Execute in specific project:
        iterare execute refactor-api --project /path/to/project

    Reuse existing workspace:
        iterare execute refactor-api --reuse refactor-api-abc12345

    Pass environment variables:
        iterare execute refactor-api --env PIP_INDEX_URL --env CUSTOM_VAR
    """
    logger.info(f"Execute command invoked with prompt: {prompt_input}")

    worktree_created = False
    worktree_name = None

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

        # 4. Resolve and parse prompt
        logger.info(f"Resolving prompt: {prompt_input}")
        prompt_path = resolve_prompt_path(prompt_input, repo_path)
        logger.info(f"Parsing prompt file: {prompt_path}")
        prompt_obj = parse_prompt_file(prompt_path)

        # 5. Determine run name and worktree
        if reuse:
            logger.info(f"Reusing existing workspace for run: {reuse}")
            run_name = reuse
            worktree_name = run_name

            worktree_path = get_worktree_path(repo_path, run_name)

            if not worktree_exists(repo_path, run_name):
                error_msg = (
                    f"Worktree for run '{run_name}' does not exist. Cannot reuse."
                )
                logger.error(error_msg)
                typer.echo(f"Error: {error_msg}", err=True)
                raise typer.Exit(1)

            logger.info(f"Found existing worktree at: {worktree_path}")
            branch = "N/A"
            prompt_name = get_workspace_name_from_prompt(prompt_obj)
        else:
            prompt_name = get_workspace_name_from_prompt(prompt_obj)
            run_name = generate_run_name(prompt_name)
            worktree_name = run_name
            branch = prompt_obj.metadata.branch or get_current_branch(repo_path)
            logger.info(f"Generated run name: {run_name} (prompt: {prompt_name})")

        # 6. Get Docker client
        logger.info("Connecting to Docker")
        docker_client = get_docker_client()

        # 7. Validate execution requirements
        validate_launch_requirements(config, docker_client, run_name)

        # 8. Create git worktree (only if not reusing)
        if not reuse:
            logger.info(f"Creating worktree for run: {run_name}")
            worktree_path = create_worktree(repo_path, run_name, branch)
            worktree_created = True
            logger.info(f"Worktree created at: {worktree_path}")

        # 9. Prepare workspace (write config and prompt files)
        logger.info("Preparing workspace with Claude Code configuration")
        prepare_workspace(worktree_path, prompt_obj.content)

        # 10. Resolve environment variables if provided
        environment_vars = None
        if env is not None and isinstance(env, list):
            logger.info(f"Resolving {len(env)} environment variables from host")
            environment_vars = resolve_environment_variables(env)

        # 11. Build execution config
        credentials_path = get_claude_credentials_path(config)
        claude_config_file = credentials_path / ".claude.json"
        exec_config = ExecutionConfig(
            image_name=config.docker.image,
            worktree_path=worktree_path,
            workspace_name=run_name,
            claude_credentials_path=credentials_path,
            claude_config_file=claude_config_file,
            prompt_content=prompt_obj.content,
            allowed_domains=config.firewall.allowed_domains,
            environment=environment_vars,
        )

        # 12. Launch Docker container
        logger.info(f"Launching Docker container for run: {run_name}")
        container_id = launch_container(docker_client, exec_config, run_name)
        logger.info(f"Container launched with ID: {container_id}")

        # 13. Register run in cache (only if not reusing)
        if not reuse:
            register_run(repo_path, run_name, prompt_name)

        # 14. Display success message
        display_success_message(run_name, container_id, worktree_path, branch)

    except KeyboardInterrupt:
        typer.echo("\n\nInterrupted. Rolling back worktree...", err=True)
        if worktree_created and worktree_name:
            cleanup_on_interrupt(repo_path, worktree_name)
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

    except CredentialsNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        typer.echo(
            "\nPlease ensure Claude Code is configured with valid credentials.",
            err=True,
        )
        raise typer.Exit(1)

    except IterareError as e:
        typer.echo(f"Error: {e}", err=True)
        logger.exception("Execution failed")
        raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error during execution")
        raise typer.Exit(1)
