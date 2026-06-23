"""List command for viewing persisted Claude conversations."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from iterare_llm.commands.common import resolve_project_dir
from iterare_llm.conversations import list_conversations
from iterare_llm.logging import get_logger

logger = get_logger(__name__)
console = Console()


def display_conversations_table(conversations: list, title: str) -> None:
    """
    Display conversations in a formatted table.

    Parameters
    ----------
    conversations : list
        List of `Conversation` objects
    title : str
        Table title
    """
    table = Table(title=title, header_style="bold magenta")
    table.add_column("Session ID", style="cyan", no_wrap=True)
    table.add_column("Modified", style="yellow", no_wrap=True)
    table.add_column("Branch", style="green")
    table.add_column("Description")

    for conversation in conversations:
        table.add_row(
            conversation.session_id,
            conversation.modified_display(),
            conversation.git_branch or "-",
            conversation.short_description() or "-",
        )

    console.print(table)


def conversations_command(
    project_dir: Optional[Path] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project directory (defaults to current directory)",
    ),
) -> None:
    """
    List persisted Claude conversations for the project.

    Shows the conversations available to resume with `iterare execute --resume`
    or `iterare interactive --resume`, newest first.

    Examples
    --------
    List conversations for the current project:
        iterare conversations

    List for a specific project:
        iterare conversations --project /path/to/project
    """
    logger.info("Conversations command invoked")

    try:
        project_dir = resolve_project_dir(project_dir)

        conversations = list_conversations(project_dir)
        if not conversations:
            typer.echo("No conversations found for this project.")
            return

        display_conversations_table(conversations, "💬 Conversations")
        typer.echo()
        typer.echo(f"Total: {len(conversations)} conversation(s)")
        typer.echo("Resume one with: iterare interactive --resume <session-id>")

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        logger.exception("Conversations command failed")
        raise typer.Exit(1)
