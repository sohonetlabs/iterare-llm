"""List command for viewing execution runs."""

from pathlib import Path
from typing import Optional

import docker
import typer
from rich.console import Console
from rich.table import Table

from iterare_llm.commands.common import resolve_project_dir
from iterare_llm.docker import (
    get_docker_client,
    find_container_by_name,
    generate_container_name,
)
from iterare_llm.git import is_git_repository, worktree_exists
from iterare_llm.logging import get_logger
from iterare_llm.run import list_runs

logger = get_logger(__name__)
console = Console()


def get_run_status(
    run_name: str,
    project_dir: Path,
    docker_client: docker.DockerClient,
) -> str:
    """
    Determine the status of a run.

    Parameters
    ----------
    run_name : str
        Name of the run
    project_dir : Path
        Project directory path
    docker_client : docker.DockerClient
        Docker client for checking container status

    Returns
    -------
    str
        Status: "active", "finished", or "cleaned"
    """
    container_name = generate_container_name(run_name)
    container = find_container_by_name(docker_client, container_name)

    # Check if container is running
    if container and container.status == "running":
        return "active"

    # Check if worktree still exists (finished but not cleaned up)
    if worktree_exists(project_dir, run_name):
        return "finished"

    # Otherwise, it's been cleaned up
    return "cleaned"


def display_runs_table(runs: list[dict], title: str) -> None:
    """
    Display runs in a formatted table.

    Parameters
    ----------
    runs : list[dict]
        List of run metadata dictionaries
    title : str
        Table title
    """
    if not runs:
        return

    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Run Name", style="cyan", no_wrap=True)
    table.add_column("Prompt", style="green")
    table.add_column("Status", style="yellow")

    for run in runs:
        run_name = run["run_name"]
        prompt_name = run.get("prompt_name", "unknown")
        status = run.get("status", "unknown")

        table.add_row(run_name, prompt_name, status)

    console.print(table)


def list_command(
    project_dir: Optional[Path] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project directory (defaults to current directory)",
    ),
    all_runs: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show all runs including cleaned up ones",
    ),
) -> None:
    """
    List execution runs for the project.

    Shows active runs (currently executing), finished runs (completed but not
    cleaned up), and optionally all previous runs including those that have
    been cleaned up.

    Examples
    --------
    List active and finished runs:
        iterare list

    List all runs including cleaned up ones:
        iterare list --all

    List for specific project:
        iterare list --project /path/to/project
    """
    logger.info("List command invoked")

    try:
        project_dir = resolve_project_dir(project_dir)

        # Verify this is a git repository
        if not is_git_repository(project_dir):
            typer.echo(f"Error: Not a git repository: {project_dir}", err=True)
            raise typer.Exit(1)

        # Get all runs
        all_runs_list = list_runs(project_dir)

        if not all_runs_list:
            typer.echo("No runs found for this project.")
            return

        # Get Docker client for checking container status
        try:
            docker_client = get_docker_client()
        except Exception as e:
            logger.warning(f"Failed to connect to Docker: {e}")
            typer.echo(
                "Warning: Could not connect to Docker. Run status may be incomplete.",
                err=True,
            )
            # Continue without Docker - all runs will appear as "cleaned"
            docker_client = None

        # Categorize runs by status
        active_runs = []
        finished_runs = []
        cleaned_runs = []

        for run in all_runs_list:
            run_name = run["run_name"]

            if docker_client:
                status = get_run_status(run_name, project_dir, docker_client)
            else:
                # Without Docker, check only worktree
                if worktree_exists(project_dir, run_name):
                    status = "finished"
                else:
                    status = "cleaned"

            run["status"] = status

            if status == "active":
                active_runs.append(run)
            elif status == "finished":
                finished_runs.append(run)
            else:
                cleaned_runs.append(run)

        # Display active runs
        if active_runs:
            display_runs_table(active_runs, "🚀 Active Runs")
            typer.echo()

        # Display finished runs
        if finished_runs:
            display_runs_table(finished_runs, "✅ Finished Runs")
            typer.echo()

        # Display all runs if --all flag is set
        if all_runs:
            if cleaned_runs:
                display_runs_table(cleaned_runs, "🗑️  Cleaned Up Runs")
                typer.echo()

        # Summary
        typer.echo(f"Total: {len(all_runs_list)} runs")
        if not all_runs and cleaned_runs:
            typer.echo(
                f"({len(cleaned_runs)} cleaned up runs hidden. Use --all to show them.)"
            )

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        logger.exception("List command failed")
        raise typer.Exit(1)
