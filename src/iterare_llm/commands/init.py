"""Initialize a project for iterare."""

from pathlib import Path
from textwrap import dedent
from typing import Optional

import typer

from iterare_llm.config import (
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_SHELL,
    DEFAULT_CREDENTIALS_PATH,
)
from iterare_llm.logging import get_logger

logger = get_logger(__name__)


DOCKERFILE_TEMPLATE = dedent(f"""
    FROM {DEFAULT_DOCKER_IMAGE}

    # Modify from the base Dockerfile for your needs
    """).lstrip()

CONFIG_TEMPLATE = dedent(f"""
    [docker]
    image = "{DEFAULT_DOCKER_IMAGE}"

    [session]
    shell = "{DEFAULT_SHELL}"

    [claude]
    credentials_path = "{DEFAULT_CREDENTIALS_PATH}"

    [firewall]
    # Additional domains to allow through the firewall
    # Default domains (npm, anthropic, github, etc.) are always included
    allowed_domains = [
        # Add custom domains here, e.g.:
        # "pypi.org",
        # "files.pythonhosted.org",
    ]
    """).lstrip()

EXAMPLE_PROMPT_TEMPLATE = dedent("""
    ---
    workspace: example-task  # Optional: custom worktree name
    
    ---
    
    # Example Prompt for Claude Code
    
    Your prompt for Claude goes here. Claude will execute this in dangerous mode,
    meaning it will autonomously make file changes, run commands, and perform
    actions without asking for permission.
    
    ## Example Task
    
    Please analyze the codebase and:
    1. Identify any TODO comments
    2. Create a summary document listing all TODOs
    3. Run the test suite to ensure everything passes
    
    ## Expected Behavior
    
    Claude will:
    - Search through files for TODO comments
    - Create a new markdown file with findings
    - Execute the test command
    - Report results
    """).lstrip()


def init_project(project_dir: Path, force: bool = False) -> None:
    """
    Initialize a project for iterare.

    Creates the .iterare directory with configuration files,
    the prompts subdirectory, and the workspaces directory for git worktrees.

    Parameters
    ----------
    project_dir : Path
        The project directory to initialize
    force : bool, optional
        If True, overwrite existing files. Default is False.

    Raises
    ------
    FileExistsError
        If .iterare already exists and force is False
    PermissionError
        If unable to create directories or write files due to permissions
    OSError
        If an error occurs during file or directory creation
    """
    iterare_dir = project_dir / ".iterare"
    prompts_dir = iterare_dir / "prompts"
    workspaces_dir = project_dir / "workspaces"

    logger.debug(f"Initializing iterare in {project_dir}")

    # Check if already initialized
    if iterare_dir.exists() and not force:
        logger.warning(f"Directory {iterare_dir} already exists, force flag not set")
        raise FileExistsError(
            f".iterare directory already exists at {iterare_dir}. "
            "Use --force to overwrite."
        )

    try:
        # Create directories
        logger.debug(f"Creating directory: {iterare_dir}")
        iterare_dir.mkdir(exist_ok=True)

        logger.debug(f"Creating directory: {prompts_dir}")
        prompts_dir.mkdir(exist_ok=True)

        logger.debug(f"Creating directory: {workspaces_dir}")
        workspaces_dir.mkdir(exist_ok=True)

        # Create Dockerfile
        dockerfile_path = iterare_dir / "Dockerfile"
        logger.debug(f"Writing file: {dockerfile_path}")
        dockerfile_path.write_text(DOCKERFILE_TEMPLATE)

        # Create config.toml
        config_path = iterare_dir / "config.toml"
        logger.debug(f"Writing file: {config_path}")
        config_path.write_text(CONFIG_TEMPLATE)

        # Create example prompt in prompts subdirectory
        example_prompt_path = prompts_dir / "example-prompt.md"
        logger.debug(f"Writing file: {example_prompt_path}")
        example_prompt_path.write_text(EXAMPLE_PROMPT_TEMPLATE)

        # Update .gitignore
        logger.debug("Updating .gitignore")
        _update_gitignore(project_dir)

        logger.info(f"Successfully initialized iterare in {project_dir}")

    except PermissionError as e:
        logger.error(f"Permission denied while initializing: {e}")
        raise PermissionError(
            f"Permission denied: Unable to create directories or write files in {project_dir}. "
            "Check your file permissions."
        ) from e
    except OSError as e:
        logger.error(f"Error during initialization: {e}")
        raise OSError(f"Failed to initialize project: {e}") from e


def _update_gitignore(project_dir: Path) -> None:
    """
    Update .gitignore to include workspaces directory.

    Parameters
    ----------
    project_dir : Path
        The project directory containing .gitignore
    """
    gitignore_path = project_dir / ".gitignore"

    # Read existing .gitignore or create empty list
    if gitignore_path.exists():
        lines = gitignore_path.read_text().splitlines()
    else:
        lines = []

    # Check if workspaces/ is already in .gitignore
    if "workspaces/" not in lines and "workspaces" not in lines:
        # Add a blank line if file is not empty and doesn't end with newline
        if lines and lines[-1] != "":
            lines.append("")
        lines.append("# iterare workspaces")
        lines.append("workspaces/")

        # Write back to .gitignore
        gitignore_path.write_text("\n".join(lines) + "\n")


def init(
    path: Optional[Path] = typer.Argument(
        None,
        help="Path to initialize (defaults to current directory)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing configuration",
    ),
) -> None:
    """
    Initialize a project for iterare.

    Creates the .iterare directory with:
    - Dockerfile (based on iterare-llm:latest)
    - config.toml (default configuration)
    - prompts/ subdirectory for storing prompt files
    - prompts/example-prompt.md (example prompt template)

    Also creates the workspaces/ directory for git worktrees and updates
    .gitignore to exclude it.
    """
    project_dir = path if path else Path.cwd()

    try:
        init_project(project_dir, force=force)
        typer.echo(f"Initialized iterare in {project_dir}")
        typer.echo("\nCreated:")
        typer.echo("  .iterare/Dockerfile")
        typer.echo("  .iterare/config.toml")
        typer.echo("  .iterare/prompts/")
        typer.echo("  .iterare/prompts/example-prompt.md")
        typer.echo("  workspaces/")
        typer.echo("\nUpdated .gitignore to exclude workspaces/")
        typer.echo(
            "\nNext steps:\n"
            "  1. Review and customize .iterare/Dockerfile if needed\n"
            "  2. Review .iterare/config.toml\n"
            "  3. See .iterare/prompts/example-prompt.md for prompt format\n"
            "  4. Create your own prompts in .iterare/prompts/\n"
        )
    except FileExistsError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except (PermissionError, OSError) as e:
        typer.echo(f"Error initializing project: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        logger.exception("Unexpected error during initialization")
        typer.echo(f"Error initializing project: {e}", err=True)
        raise typer.Exit(1)
