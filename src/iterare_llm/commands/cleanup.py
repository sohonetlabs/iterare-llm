"""Clean up git worktree and branch for a run."""

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
    is_git_repository,
    remove_branch,
    remove_worktree,
    worktree_exists,
)
from iterare_llm.logging import get_logger

logger = get_logger(__name__)


def cleanup(
    run_name: Optional[str] = typer.Argument(
        None,
        help="Run name to clean up (defaults to most recent run)",
        autocompletion=run_name_autocomplete,
    ),
    project_dir: Optional[Path] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project directory (defaults to current directory)",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt and proceed with cleanup",
    ),
) -> None:
    """
    Clean up git worktree and branch for a run.

    This command removes the git worktree and associated branch for a specific run.
    The worktree is always deleted first, followed by the branch. Both operations
    use the --force flag to handle any uncommitted changes.

    Note: The log file for the run is preserved and not deleted.

    Examples
    --------
    Clean up most recent run (with confirmation):
        iterare cleanup

    Clean up specific run:
        iterare cleanup refactor-api-abc123

    Skip confirmation prompt:
        iterare cleanup -y

    Clean up specific run without confirmation:
        iterare cleanup refactor-api-abc123 -y
    """
    logger.info(f"Cleanup command invoked for run: {run_name}")

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

    worktree_present = worktree_exists(project_dir, run_name)
    branch_present = branch_exists(project_dir, run_name)

    if not worktree_present and not branch_present:
        typer.echo(
            f"Nothing to clean up for run '{run_name}': worktree and branch do not exist"
        )
        raise typer.Exit(0)

    typer.echo(f"\nCleanup for run: {run_name}")
    if worktree_present:
        typer.echo(f"  \u2022 Worktree: workspaces/{run_name}")
    if branch_present:
        typer.echo(f"  \u2022 Branch: {run_name}")
    typer.echo()

    if not yes:
        confirmation = typer.confirm(
            "Do you want to proceed with cleanup?", default=False
        )
        if not confirmation:
            typer.echo("Cleanup cancelled")
            raise typer.Exit(0)

    try:
        if worktree_present:
            logger.info(f"Removing worktree for run: {run_name}")
            remove_worktree(project_dir, run_name)
            typer.echo(f"\u2713 Removed worktree: workspaces/{run_name}")

        if branch_present:
            logger.info(f"Removing branch for run: {run_name}")
            remove_branch(project_dir, run_name)
            typer.echo(f"\u2713 Removed branch: {run_name}")

        typer.echo(f"\nCleanup completed for run: {run_name}")
        typer.echo("Note: Log file has been preserved")

    except Exception as e:
        typer.echo(f"\nError during cleanup: {e}", err=True)
        logger.exception("Cleanup failed")
        raise typer.Exit(1)
