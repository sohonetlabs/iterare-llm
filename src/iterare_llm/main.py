import typer
from typing_extensions import Annotated

from iterare_llm.commands.credentials import credentials as credentials_command
from iterare_llm.commands.init import init
from iterare_llm.commands.execute import execute as execute_command
from iterare_llm.commands.install import install
from iterare_llm.commands.interactive import interactive as interactive_command
from iterare_llm.commands.log import log
from iterare_llm.commands.cleanup import cleanup
from iterare_llm.commands.list import list_command
from iterare_llm.commands.merge import merge
from iterare_llm.logging import setup_logging
from iterare_llm import __version__


app = typer.Typer(
    name="iterare",
    help="Automated Claude Code execution in isolated environments",
    no_args_is_help=True,
)

# Global state for verbose flag
verbose_mode = False

# Add commands
app.command(name="install", help="Install iterare by creating global config directory")(
    install
)
app.command(
    name="credentials",
    help="Fetch Claude Code credentials via interactive Docker session",
)(credentials_command)
app.command(name="init", help="Initialize a project for iterare")(init)
app.command(name="execute", help="Execute a prompt in isolated container")(
    execute_command
)
app.command(
    name="interactive", help="Launch interactive Claude Code session in container"
)(interactive_command)
app.command(name="log", help="View logs for a run")(log)
app.command(name="cleanup", help="Clean up git worktree and branch for a run")(cleanup)
app.command(name="list", help="List execution runs for the project")(list_command)
app.command(name="merge", help="Merge worktree branch back into current branch")(merge)


@app.callback(invoke_without_command=True)
def callback(
    _: typer.Context,
    version: Annotated[
        bool,
        typer.Option("--version", help="Show version information"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose logging"),
    ] = False,
):
    """
    Automated Claude Code execution in isolated environments.

    Global options that apply to all commands.
    """
    setup_logging(verbose=verbose)

    if version:
        typer.echo(f"iterare version {__version__}")
        raise typer.Exit()


def main():  # pragma: no cover
    """CLI entry point."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
