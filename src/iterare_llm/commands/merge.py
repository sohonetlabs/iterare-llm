"""Merge worktree branch back into the current branch."""

from pathlib import Path
from typing import Optional

import typer

from iterare_llm.commands.common import (
    get_current_run,
    resolve_project_dir,
    run_name_autocomplete,
)
from iterare_llm.git import (
    branch_exists,
    get_current_branch,
    is_git_repository,
    merge_branch,
)
from iterare_llm.logging import get_logger

logger = get_logger(__name__)


def merge(
    run_name: Optional[str] = typer.Argument(
        None,
        help="Run name to merge (defaults to most recent run)",
        autocompletion=run_name_autocomplete,
    ),
    project_dir: Optional[Path] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project directory (defaults to current directory)",
    ),
) -> None:
    """
    Merge worktree branch back into the current branch.

    This command merges the branch associated with a specific run back into
    the current branch. The worktree branch must exist for the merge to proceed.

    Examples
    --------
    Merge most recent run:
        iterare merge

    Merge specific run:
        iterare merge refactor-api-abc123

    Merge in specific project:
        iterare merge --project /path/to/project
    """
    logger.info(f"Merge command invoked for run: {run_name}")

    project_dir = resolve_project_dir(project_dir)

    if not is_git_repository(project_dir):
        error_msg = f"Not a git repository: {project_dir}"
        logger.error(error_msg)
        typer.echo(f"Error: {error_msg}", err=True)
        raise typer.Exit(1)

    if run_name is None:
        run_name = get_current_run(project_dir)
        if run_name is None:
            typer.echo(
                "Error: No runs found for this project.\n"
                "Execute a prompt first with: iterare execute <prompt>",
                err=True,
            )
            raise typer.Exit(1)
        logger.debug(f"Using most recent run: {run_name}")

    if not branch_exists(project_dir, run_name):
        typer.echo(
            f"Error: Branch '{run_name}' does not exist.\n"
            "The run may have been cleaned up or never existed.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        current_branch = get_current_branch(project_dir)
    except Exception as e:
        typer.echo(f"Error: Unable to determine current branch: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\nMerging branch '{run_name}' into '{current_branch}'...")

    try:
        merge_branch(project_dir, run_name)
        typer.echo(f"\u2713 Successfully merged '{run_name}' into '{current_branch}'")
    except Exception as e:
        typer.echo(f"\nError during merge: {e}", err=True)
        logger.exception("Merge failed")
        raise typer.Exit(1)
