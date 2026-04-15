"""View logs for a iterare run."""

import json
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.text import Text

from iterare_llm.commands.common import (
    get_current_run,
    resolve_project_dir,
    run_name_autocomplete,
)
from iterare_llm.logging import get_logger
from iterare_llm.paths import get_log_file_path
from iterare_llm.run import list_runs, load_runs_metadata

logger = get_logger(__name__)
console = Console()


def format_stream_json_line(line: dict, verbosity: int) -> Optional[Text]:
    """
    Format a stream-json line for display.

    Parameters
    ----------
    line : dict
        Parsed JSON line
    verbosity : int
        Verbosity level (0=minimal, 1=normal, 2=verbose)

    Returns
    -------
    Text | None
        Formatted text, or None if line should be skipped

    Examples
    --------
    >>> line = {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}
    >>> format_stream_json_line(line, 1)
    Text('💬 Claude: Hello')
    """
    line_type = line.get("type")

    if line_type == "assistant":
        content_items = line.get("message", {}).get("content", [])
        texts = []
        for item in content_items:
            if item.get("type") == "text":
                text = Text()
                text.append("💬 Claude: ", style="bold cyan")
                text.append(item.get("text", ""))
                texts.append(text)
            elif item.get("type") == "tool_use" and verbosity >= 1:
                text = Text()
                text.append("🔧 Tool: ", style="bold yellow")
                text.append(item.get("name", ""), style="yellow")

                # Add input description/command if available
                input_data = item.get("input", {})
                if verbosity >= 2:
                    # Verbose mode: show more details
                    if "description" in input_data:
                        text.append(f"\n   {input_data['description']}", style="dim")
                    elif "command" in input_data:
                        text.append(f"\n   {input_data['command']}", style="dim")
                    else:
                        input_str = json.dumps(input_data)
                        if len(input_str) > 200:
                            input_str = input_str[:200] + "..."
                        text.append(f"\n   {input_str}", style="dim")
                elif verbosity >= 1:
                    # Normal mode: just show basic info
                    if "description" in input_data:
                        text.append(f"\n   {input_data['description']}", style="dim")
                    elif "command" in input_data:
                        text.append(f"\n   {input_data['command']}", style="dim")

                texts.append(text)

        return Text("\n").join(texts) if texts else None

    elif line_type == "user" and verbosity >= 1:
        content_items = line.get("message", {}).get("content", [])
        texts = []
        for item in content_items:
            if item.get("type") == "tool_result":
                text = Text()
                text.append("📦 Result: ", style="bold green")
                content = item.get("content", "")
                if verbosity >= 2:
                    # Verbose mode: show full result (up to 500 chars)
                    if len(content) > 500:
                        content = content[:500] + "..."
                else:
                    # Normal mode: truncate at 200 chars
                    if len(content) > 200:
                        content = content[:200] + "..."
                text.append(content, style="dim")
                texts.append(text)

        return Text("\n").join(texts) if texts else None

    elif line_type == "result":
        text = Text()
        text.append("\n✅ Complete ", style="bold green")
        duration_s = line.get("duration_ms", 0) / 1000
        cost = line.get("total_cost_usd", 0)
        turns = line.get("num_turns", 0)
        text.append(f"in {duration_s:.1f}s ", style="green")
        text.append(f"(cost: ${cost:.4f})\n", style="green")
        text.append(f"   Turns: {turns}", style="dim green")
        return text

    elif line_type == "error":
        text = Text()
        text.append("❌ Error: ", style="bold red")
        text.append(line.get("error", {}).get("message", "Unknown error"), style="red")
        return text

    return None


def display_log_pretty(log_file: Path, verbosity: int, follow: bool) -> None:
    """
    Display log in pretty format.

    Parameters
    ----------
    log_file : Path
        Path to log file
    verbosity : int
        Verbosity level (0=minimal, 1=normal, 2=verbose)
    follow : bool
        If True, follow log file (tail -f behavior)
    """
    if not log_file.exists():
        console.print(
            f"[yellow]Log file not found: {log_file}[/yellow]\n"
            f"[dim]The container may not have started yet, or logs are empty.[/dim]"
        )
        return

    # Track position for follow mode
    file_pos = 0

    try:
        if follow:  # pragma: no cover
            console.print(
                f"[dim]Following log file: {log_file}[/dim]",
                "[dim]Press Ctrl+C to stop[/dim]\n",
            )

        while True:
            with open(log_file, "r") as f:
                if follow:  # pragma: no cover
                    f.seek(file_pos)

                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        formatted = format_stream_json_line(data, verbosity)
                        if formatted:
                            console.print(formatted)
                    except json.JSONDecodeError:
                        if verbosity >= 2:
                            console.print(f"[dim]{line}[/dim]")

                file_pos = f.tell()

            if not follow:
                break

            time.sleep(0.5)  # pragma: no cover

    except KeyboardInterrupt:  # pragma: no cover
        console.print("\n[dim]Stopped following log[/dim]")


def display_log_raw(log_file: Path, follow: bool) -> None:
    """
    Display log in raw JSON format.

    Parameters
    ----------
    log_file : Path
        Path to log file
    follow : bool
        If True, follow log file (tail -f behavior)
    """
    if not log_file.exists():
        console.print(
            f"[yellow]Log file not found: {log_file}[/yellow]"
        )
        return

    file_pos = 0

    try:
        if follow:  # pragma: no cover
            console.print(
                "[dim]Following log file (raw JSON). Press Ctrl+C to stop[/dim]\n",
            )

        while True:
            with open(log_file, "r") as f:
                if follow:  # pragma: no cover
                    f.seek(file_pos)

                for line in f:
                    line = line.strip()
                    if line:
                        console.print(line)

                file_pos = f.tell()

            if not follow:
                break

            time.sleep(0.5)  # pragma: no cover

    except KeyboardInterrupt:  # pragma: no cover
        console.print("\n[dim]Stopped following log[/dim]")


def log(
    run_name: Optional[str] = typer.Argument(
        None,
        help="Run name to view logs for (defaults to most recent run)",
        autocompletion=run_name_autocomplete,
    ),
    project_dir: Optional[Path] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project directory (defaults to current directory)",
    ),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Follow log output (like tail -f)",
    ),
    raw: bool = typer.Option(
        False,
        "--raw",
        help="Output raw JSON instead of pretty format",
    ),
    verbosity: int = typer.Option(
        1,
        "--verbosity",
        "-v",
        min=0,
        max=2,
        help="Verbosity level: 0=minimal (only Claude responses), 1=normal (responses + tools), 2=verbose (all details)",
    ),
) -> None:
    """
    View logs for a iterare run.

    By default, displays logs for the most recent run in a pretty format.
    Use --raw to see the raw JSON stream output.

    Examples
    --------
    View most recent run:
        iterare log

    View specific run:
        iterare log refactor-api-abc123

    Follow live output:
        iterare log -f

    Raw JSON output:
        iterare log --raw

    Minimal verbosity (only Claude's text responses):
        iterare log -v 0

    Verbose output (all details):
        iterare log -v 2
    """
    logger.info(f"Log command invoked for run: {run_name}")

    project_dir = resolve_project_dir(project_dir)

    # If no run name specified, use most recent
    if run_name is None:
        run_name = get_current_run(project_dir)
        if run_name is None:
            console.print(
                "[yellow]No runs found for this project.[/yellow]\n"
                "[dim]Execute a prompt first with: iterare execute <prompt>[/dim]"
            )
            raise typer.Exit(1)
        logger.debug(f"Using most recent run: {run_name}")
    else:
        # Verify run exists
        metadata = load_runs_metadata(project_dir)
        if run_name not in metadata:
            console.print(f"[red]Run not found: {run_name}[/red]")
            console.print(
                "\n[dim]Available runs:[/dim]",
            )
            runs = list_runs(project_dir)
            for run in runs[:5]:  # Show up to 5 most recent
                console.print(f"  {run['run_name']}")
            raise typer.Exit(1)

    # Get log file path
    log_file = get_log_file_path(run_name)
    logger.info(f"Log file: {log_file}")

    # Display log
    if raw:
        display_log_raw(log_file, follow)
    else:
        display_log_pretty(log_file, verbosity, follow)
